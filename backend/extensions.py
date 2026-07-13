import ssl
from datetime import datetime
from math import ceil
from urllib.parse import parse_qsl, unquote_plus, urlparse

import pymysql
from flask import current_app, g
from flask_login import LoginManager
from flask_session import Session as FlaskSession
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_bcrypt import Bcrypt


class Column:
    def __init__(self, *args, **kwargs):
        self.name = None
        self.model = None
        self.kwargs = kwargs
        self.column_type = None
        self.column_name = None

        if len(args) == 1:
            self.column_type = args[0]
        elif len(args) == 2 and isinstance(args[0], str):
            self.column_name = args[0]
            self.column_type = args[1]
        elif args:
            self.column_type = args[0]

    def __set_name__(self, owner, name):
        self.name = name
        self.model = owner
        if self.column_name is None:
            self.column_name = name

    def __get__(self, instance, owner):
        if instance is None:
            return ColumnExpression(owner, self.name)
        return instance.__dict__.get(self.name)

    def __set__(self, instance, value):
        instance.__dict__[self.name] = value


class ForeignKey:
    def __init__(self, target, name=None, **kwargs):
        self.target = target
        self.name = name
        # store any legacy ORM-style flags (use_alter, ondelete, etc.) for compatibility
        for k, v in kwargs.items():
            setattr(self, k, v)


class Relationship:
    def __init__(self, target, back_populates=None, uselist=False, lazy="select", cascade=None, **kwargs):
        self.target = target
        self.back_populates = back_populates
        self.uselist = uselist
        self.lazy = lazy
        self.cascade = cascade
        self.name = None
        self.owner = None
        # accept legacy ORM-style kwargs (foreign_keys, post_update, uselist, etc.)
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __set_name__(self, owner, name):
        self.name = name
        self.owner = owner

    def _resolve_target(self):
        if isinstance(self.target, str):
            return ModelMeta.registry[self.target]
        return self.target

    def _find_local_foreign_key(self, instance, target_cls):
        for key, column in instance.__class__._columns.items():
            fk = column.kwargs.get("foreign_key")
            if isinstance(fk, ForeignKey):
                target_table, target_column = fk.target.split(".")
                if target_table == target_cls.__tablename__:
                    return getattr(instance.__class__, key), getattr(instance, key)
        return None, None

    def _find_remote_foreign_key(self, instance, target_cls):
        for key, column in target_cls._columns.items():
            fk = column.kwargs.get("foreign_key")
            if isinstance(fk, ForeignKey):
                target_table, target_column = fk.target.split(".")
                if target_table == instance.__class__.__tablename__:
                    return getattr(target_cls, key), getattr(instance, instance.__class__._primary_key)
        return None, None

    def _build_condition(self, instance, target_cls):
        local_col, local_value = self._find_local_foreign_key(instance, target_cls)
        if local_col is not None:
            return getattr(target_cls, target_cls._primary_key) == local_value

        remote_col, remote_id = self._find_remote_foreign_key(instance, target_cls)
        if remote_col is not None:
            return remote_col == remote_id

        raise RuntimeError(
            f"Tidak dapat menentukan relasi untuk {instance.__class__.__name__}.{self.name}"
        )

    def __get__(self, instance, owner):
        if instance is None:
            return self
        if self.name in instance.__dict__:
            return instance.__dict__[self.name]

        target_cls = self._resolve_target()
        condition = self._build_condition(instance, target_cls)
        where_sql, params = condition.compile()
        select_sql = f"SELECT * FROM `{target_cls.__tablename__}` WHERE {where_sql}"

        if self.uselist or self.lazy == "dynamic":
            query = RelationshipQuery(target_cls, select_sql, params)
            instance.__dict__[self.name] = query
            return query

        row = default_db.fetchone(select_sql, params)
        value = target_cls.from_row(row) if row else None
        instance.__dict__[self.name] = value
        return value

    def __set__(self, instance, value):
        instance.__dict__[self.name] = value


class ColumnExpression:
    def __init__(self, model, name):
        self.model = model
        self.name = name

    @property
    def table_name(self):
        return getattr(self.model, "__tablename__", self.model.__name__.lower())

    @property
    def column_name(self):
        column = self.model._columns.get(self.name)
        return column.column_name if column else self.name

    def compile(self):
        return f"`{self.table_name}`.`{self.column_name}`", []

    def __eq__(self, other):
        return BinaryExpression(self, "=", other)

    def __ne__(self, other):
        return BinaryExpression(self, "!=", other)

    def is_(self, value):
        return UnaryExpression(self, value)

    def like(self, pattern):
        return BinaryExpression(self, "LIKE", pattern)

    def ilike(self, pattern):
        return BinaryExpression(FunctionExpression("LOWER", self), "LIKE", pattern.lower())

    def in_(self, values):
        return BinaryExpression(self, "IN", values)

    def notin_(self, values):
        return BinaryExpression(self, "NOT IN", values)

    def asc(self):
        return Order(self, "ASC")

    def desc(self):
        return Order(self, "DESC")

    def __str__(self):
        return f"`{self.table_name}`.`{self.column_name}`"


class ColumnType:
    def __init__(self, name, *args):
        self.name = name
        self.args = args

    def __repr__(self):
        if self.args:
            args = ",".join(str(a) for a in self.args)
            return f"{self.name}({args})"
        return self.name


class FunctionExpression:
    def __init__(self, name, *args):
        self.name = name.upper()
        self.args = args

    def compile(self):
        compiled = []
        params = []
        for arg in self.args:
            if hasattr(arg, "compile"):
                sql, arg_params = arg.compile()
                compiled.append(sql)
                params.extend(arg_params)
            else:
                compiled.append("%s")
                params.append(arg)
        return f"{self.name}({', '.join(compiled)})", params

    def __eq__(self, other):
        return BinaryExpression(self, "=", other)

    def in_(self, values):
        return BinaryExpression(self, "IN", values)

    def notin_(self, values):
        return BinaryExpression(self, "NOT IN", values)


class UnaryExpression:
    def __init__(self, left, right):
        self.left = left
        self.right = right

    def compile(self):
        left_sql, left_params = self.left.compile()
        if self.right is None:
            return f"{left_sql} IS NULL", left_params
        return f"{left_sql} = %s", left_params + [self.right]


class BinaryExpression:
    def __init__(self, left, operator, right):
        self.left = left
        self.operator = operator
        self.right = right

    def compile(self):
        left_sql, left_params = self.left.compile() if hasattr(self.left, "compile") else (str(self.left), [])
        if hasattr(self.right, "compile"):
            right_sql, right_params = self.right.compile()
            return f"{left_sql} {self.operator} {right_sql}", left_params + right_params

        if self.operator in {"IN", "NOT IN"}:
            if not isinstance(self.right, (list, tuple, set)):
                raise RuntimeError("IN/NOT IN operator requires a list, tuple, or set")
            if len(self.right) == 0:
                noop = "1=0" if self.operator == "IN" else "1=1"
                return noop, left_params
            placeholders = ", ".join(["%s"] * len(self.right))
            return f"{left_sql} {self.operator} ({placeholders})", left_params + list(self.right)

        if self.right is None:
            if self.operator == "=":
                return f"{left_sql} IS NULL", left_params
            if self.operator == "!=" or self.operator.upper() == "<>":
                return f"{left_sql} IS NOT NULL", left_params
        return f"{left_sql} {self.operator} %s", left_params + [self.right]


class BooleanExpression:
    def __init__(self, operator, conditions):
        self.operator = operator
        self.conditions = conditions

    def compile(self):
        compiled = []
        params = []
        for condition in self.conditions:
            sql, condition_params = condition.compile()
            compiled.append(f"({sql})")
            params.extend(condition_params)
        return f" {self.operator} ".join(compiled), params


class Order:
    def __init__(self, expression, direction):
        self.expression = expression
        self.direction = direction

    def compile(self):
        sql, params = self.expression.compile()
        return f"{sql} {self.direction}", params


def or_(*conditions):
    return BooleanExpression("OR", conditions)


class Pagination:
    def __init__(self, items, page, per_page, total):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total
        self.pages = ceil(total / per_page) if per_page else 0


class ModelMeta(type):
    registry = {}

    def __new__(mcs, name, bases, attrs):
        columns = {}
        relationships = {}

        for base in bases:
            if hasattr(base, "_columns"):
                columns.update(base._columns)
            else:
                for attr_name, attr_value in vars(base).items():
                    if isinstance(attr_value, Column):
                        columns[attr_name] = attr_value
            if hasattr(base, "_relationships"):
                relationships.update(base._relationships)
            else:
                for attr_name, attr_value in vars(base).items():
                    if isinstance(attr_value, Relationship):
                        relationships[attr_name] = attr_value

        for attr_name, attr_value in list(attrs.items()):
            if isinstance(attr_value, Column):
                columns[attr_name] = attr_value
            elif isinstance(attr_value, Relationship):
                relationships[attr_name] = attr_value

        cls = super().__new__(mcs, name, bases, attrs)
        cls._columns = columns
        cls._relationships = relationships
        cls._primary_key = None
        cls._table_name = getattr(cls, "__tablename__", name.lower())

        for column in columns.values():
            column.model = cls
            if column.kwargs.get("primary_key"):
                cls._primary_key = column.name or column.column_name

        if cls._primary_key is None and "id" in columns:
            cls._primary_key = "id"

        ModelMeta.registry[name] = cls
        return cls


class Model(metaclass=ModelMeta):
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self._is_persisted = False
        self._original_values = None

    def __repr__(self):
        pk = getattr(self, self.__class__._primary_key, None)
        return f"<{self.__class__.__name__} {self.__class__._primary_key}={pk}>"

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None

        data = dict(row)
        if "is_active_flag" not in data and "is_active" in data:
            data["is_active_flag"] = data["is_active"]

        if "is_deleted" in data and "deleted_at" not in data:
            data["deleted_at"] = datetime.utcnow() if bool(data["is_deleted"]) else None

        instance = cls.__new__(cls)
        for key, value in data.items():
            if key in {"is_active", "is_deleted"} and hasattr(cls, key) and isinstance(getattr(cls, key), property):
                continue
            setattr(instance, key, value)

        instance._is_persisted = True
        instance._original_values = instance.to_dict()
        return instance

    def to_dict(self):
        return {name: getattr(self, name) for name in self.__class__._columns}


class Query:
    def __init__(self, model=None, select_entities=None, db=None):
        self.model = model
        self.select_entities = list(select_entities) if select_entities is not None else None
        self.filters = []
        self.joins = []
        self.order_by_clauses = []
        self.group_by_clauses = []
        self.limit_value = None
        self.offset_value = None
        self.for_update = False
        self.distinct_flag = False
        self.db = db or default_db

        if self.model is None and self.select_entities:
            first = self.select_entities[0]
            if hasattr(first, "model"):
                self.model = first.model

    def filter(self, *conditions):
        self.filters.extend(conditions)
        return self

    def filter_by(self, **kwargs):
        for key, value in kwargs.items():
            column = getattr(self.model, key)
            self.filter(column == value)
        return self

    def join(self, target, onclause=None, isouter=False):
        self.joins.append((target, onclause, isouter))
        return self

    def outerjoin(self, target, onclause=None):
        return self.join(target, onclause, isouter=True)

    def order_by(self, *clauses):
        self.order_by_clauses.extend(clauses)
        return self

    def distinct(self):
        self.distinct_flag = True
        return self

    def with_entities(self, *entities):
        self.select_entities = list(entities)
        return self

    def with_for_update(self):
        self.for_update = True
        return self

    def group_by(self, *clauses):
        self.group_by_clauses.extend(clauses)
        return self

    def scalar(self):
        row = self.limit(1).all()
        if not row:
            return None
        first = row[0]
        if isinstance(first, tuple):
            return first[0] if first else None
        if hasattr(first, "__iter__") and not isinstance(first, dict):
            return next(iter(first), None)
        return first

    def limit(self, limit):
        self.limit_value = limit
        return self

    def offset(self, offset):
        self.offset_value = offset
        return self

    def first(self):
        results = self.limit(1).all()
        return results[0] if results else None

    def all(self):
        cursor = self._execute()
        return self._rows_from_cursor(cursor)

    def count(self):
        sql, params = self._compile_count()
        cursor = self.db.execute(sql, params)
        row = cursor.fetchone()
        return int(row["count"] if row and "count" in row else 0)

    def paginate(self, page=1, per_page=10, error_out=False):
        total = self.count()
        page = max(1, page)
        offset = (page - 1) * per_page
        items = self.limit(per_page).offset(offset).all()
        return Pagination(items, page, per_page, total)

    def _rows_from_cursor(self, cursor):
        rows = cursor.fetchall()
        if self.select_entities is not None:
            return [tuple(row.values()) for row in rows]
        instances = []
        for row in rows:
            instance = self.model(**row)
            instance._is_persisted = True
            instance._original_values = instance.to_dict()
            instances.append(instance)
        return instances

    def _compile_count(self):
        base = self.model
        if self.joins:
            column = f"`{base.__tablename__}`.`{base._primary_key}`"
            select_clause = f"COUNT(DISTINCT {column}) AS count"
        else:
            select_clause = "COUNT(*) AS count"
        from_clause = f"`{base.__tablename__}`"
        join_clause, params = self._compile_joins()
        where_clause, where_params = self._compile_filters()
        sql = f"SELECT {select_clause} FROM {from_clause}{join_clause}{where_clause}"
        return sql, params + where_params

    def _compile_select(self):
        if self.select_entities is not None:
            selections = []
            params = []
            for index, entity in enumerate(self.select_entities):
                sql, entity_params = entity.compile()
                selections.append(f"{sql} AS `col_{index}`")
                params.extend(entity_params)
            select_clause = ", ".join(selections)
        else:
            select_clause = ", ".join(
                f"`{self.model.__tablename__}`.`{column.column_name}`" for column in self.model._columns.values()
            )
            params = []
        return select_clause, params

    def _compile_joins(self):
        sql_parts = []
        params = []
        for target, onclause, isouter in self.joins:
            join_type = "LEFT OUTER JOIN" if isouter else "INNER JOIN"
            target_name = getattr(target, "__tablename__", target.__name__.lower())
            if onclause is None:
                raise RuntimeError("Join condition is required for raw SQL query.")
            on_sql, on_params = onclause.compile()
            sql_parts.append(f" {join_type} `{target_name}` ON {on_sql}")
            params.extend(on_params)
        return "".join(sql_parts), params

    def _compile_filters(self):
        if not self.filters:
            return "", []
        compiled = []
        params = []
        for condition in self.filters:
            condition_sql, condition_params = condition.compile()
            compiled.append(condition_sql)
            params.extend(condition_params)
        return f" WHERE {' AND '.join(compiled)}", params

    def _compile_order_by(self):
        if not self.order_by_clauses:
            return "", []
        compiled = []
        params = []
        for clause in self.order_by_clauses:
            clause_sql, clause_params = clause.compile()
            compiled.append(clause_sql)
            params.extend(clause_params)
        return f" ORDER BY {', '.join(compiled)}", params

    def _compile_group_by(self):
        if not self.group_by_clauses:
            return "", []
        compiled = []
        params = []
        for clause in self.group_by_clauses:
            clause_sql, clause_params = clause.compile()
            compiled.append(clause_sql)
            params.extend(clause_params)
        return f" GROUP BY {', '.join(compiled)}", params

    def _compile_sql(self):
        select_clause, select_params = self._compile_select()
        from_clause = f"FROM `{self.model.__tablename__}`"
        join_clause, join_params = self._compile_joins()
        where_clause, where_params = self._compile_filters()
        group_clause, group_params = self._compile_group_by()
        order_clause, order_params = self._compile_order_by()
        limit_clause = f" LIMIT {self.limit_value}" if self.limit_value is not None else ""
        offset_clause = f" OFFSET {self.offset_value}" if self.offset_value is not None else ""
        for_update = " FOR UPDATE" if self.for_update else ""
        distinct = "DISTINCT " if self.distinct_flag else ""
        sql = f"SELECT {distinct}{select_clause} {from_clause}{join_clause}{where_clause}{group_clause}{order_clause}{limit_clause}{offset_clause}{for_update}"
        return sql, select_params + join_params + where_params + group_params + order_params

    def _execute(self):
        sql, params = self._compile_sql()
        return self.db.execute(sql, params)


class Savepoint:
    def __init__(self, session):
        self.session = session
        self.name = f"sp_{id(self)}"

    def __enter__(self):
        connection = self.session.db.get_connection()
        with connection.cursor() as cursor:
            cursor.execute(f"SAVEPOINT {self.name}")
        return self

    def __exit__(self, exc_type, exc, exc_tb):
        connection = self.session.db.get_connection()
        with connection.cursor() as cursor:
            if exc_type is not None:
                cursor.execute(f"ROLLBACK TO SAVEPOINT {self.name}")
            cursor.execute(f"RELEASE SAVEPOINT {self.name}")


class RawDatabase:
    Column = Column
    ForeignKey = ForeignKey
    relationship = staticmethod(lambda target, **kwargs: Relationship(target, **kwargs))
    String = staticmethod(lambda *args: ColumnType("VARCHAR", *args))
    BigInteger = staticmethod(lambda *args: ColumnType("BIGINT", *args))
    Integer = staticmethod(lambda *args: ColumnType("INT", *args))
    Text = staticmethod(lambda *args: ColumnType("TEXT", *args))
    Boolean = staticmethod(lambda *args: ColumnType("BOOLEAN", *args))
    Date = staticmethod(lambda *args: ColumnType("DATE", *args))
    Numeric = staticmethod(lambda *args: ColumnType("NUMERIC", *args))
    TIMESTAMP = staticmethod(lambda *args: ColumnType("TIMESTAMP", *args))

    def __init__(self):
        self.session = RawSession(self)
        self.app = None

    def init_app(self, app):
        self.app = app
        app.teardown_appcontext(self.teardown)
        app.extensions["raw_db"] = self

    def get_connection(self):
        connection = g.get("raw_db_connection")
        if connection is None:
            connection = self.connect()
            g.raw_db_connection = connection
        return connection

    def connect(self):
        database_url = current_app.config.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL belum diset di environment variable (.env).")

        parsed = urlparse(database_url)
        query = dict(parse_qsl(parsed.query))
        ssl_options = {}

        if query.get("ssl_verify_cert", "false").lower() in {"1", "true", "yes", "on"}:
            ssl_options["check_hostname"] = True
        if query.get("ssl_verify_identity", "false").lower() in {"1", "true", "yes", "on"}:
            ssl_options["check_hostname"] = True

        connect_kwargs = {
            "host": parsed.hostname,
            "user": unquote_plus(parsed.username) if parsed.username else None,
            "password": unquote_plus(parsed.password) if parsed.password else None,
            "database": parsed.path.lstrip("/"),
            "port": parsed.port or 3306,
            "cursorclass": pymysql.cursors.DictCursor,
            "autocommit": False,
            "charset": "utf8mb4",
        }

        if ssl_options:
            connect_kwargs["ssl"] = ssl_options

        return pymysql.connect(**connect_kwargs)

    def execute(self, sql, params=None):
        connection = self.get_connection()
        cursor = connection.cursor()
        cursor.execute(sql, params or ())
        return cursor

    def fetchone(self, sql, params=None):
        cursor = self.execute(sql, params)
        return cursor.fetchone()

    def fetchall(self, sql, params=None):
        cursor = self.execute(sql, params)
        return cursor.fetchall()

    def scalar(self, sql, params=None):
        row = self.fetchone(sql, params)
        if row is None:
            return None
        return next(iter(row.values()))

    def insert(self, sql, params=None):
        cursor = self.execute(sql, params)
        return cursor.lastrowid

    def commit(self):
        self.get_connection().commit()

    def rollback(self):
        self.get_connection().rollback()

    def begin_nested(self):
        return Savepoint(self.session)

    def teardown(self, exception):
        connection = g.pop("raw_db_connection", None)
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


class RawSession:
    def __init__(self, db):
        self.db = db
        self.new = []
        self.dirty = set()
        self.deleted = set()
        self.identity_map = {}

    def add(self, instance):
        if getattr(instance, "_is_persisted", False):
            self._mark_dirty(instance)
        elif instance not in self.new:
            self.new.append(instance)
        self._register(instance)

    def delete(self, instance):
        if instance in self.new:
            self.new.remove(instance)
            return

        if getattr(instance, "_is_persisted", False):
            self.deleted.add(instance)
            key = (instance.__class__, getattr(instance, instance.__class__._primary_key))
            self.identity_map.pop(key, None)

    def _mark_dirty(self, instance):
        self.dirty.add(instance)

    def _register(self, instance):
        return

    def commit(self):
        connection = self.db.get_connection()
        try:
            self.flush()
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def rollback(self):
        connection = self.db.get_connection()
        try:
            connection.rollback()
        finally:
            self.new.clear()
            self.dirty.clear()

    def flush(self):
        for instance in list(self.new):
            self._save_instance(instance)
        for instance in list(self.dirty):
            self._save_instance(instance)
        for instance in list(self.deleted):
            self._delete_instance(instance)
        self.new.clear()
        self.dirty.clear()
        self.deleted.clear()

    def begin_nested(self):
        return Savepoint(self)

    def query(self, *entities):
        return Query(select_entities=entities, db=self.db)

    def _save_instance(self, instance):
        model = instance.__class__
        pk_name = model._primary_key
        pk_value = getattr(instance, pk_name, None)

        if pk_value is None:
            columns = []
            values = []
            for name, column in model._columns.items():
                if name == pk_name:
                    continue
                value = getattr(instance, name)
                if value is None and column.kwargs.get("server_default") is not None:
                    continue
                if value is None and column.kwargs.get("default") is None and column.column_name in {"created_at", "updated_at", "deleted_at"}:
                    continue
                columns.append(column.column_name)
                values.append(value)

            placeholders = ", ".join(["%s"] * len(columns))
            column_list = ", ".join(f"`{col}`" for col in columns)
            sql = f"INSERT INTO `{model.__tablename__}` ({column_list}) VALUES ({placeholders})"
            with self.db.get_connection().cursor() as cursor:
                cursor.execute(sql, values)
                instance_id = cursor.lastrowid
                setattr(instance, pk_name, instance_id)
        else:
            if getattr(instance, "_original_values", None) is None:
                self._original_values = instance.to_dict()
            changes = []
            params = []
            for name, column in model._columns.items():
                if name == pk_name:
                    continue
                current_value = getattr(instance, name)
                original_value = instance._original_values.get(name) if instance._original_values else None
                if current_value != original_value:
                    changes.append(f"`{column.column_name}` = %s")
                    params.append(current_value)
            if changes:
                params.append(pk_value)
                sql = f"UPDATE `{model.__tablename__}` SET {', '.join(changes)} WHERE `{model._columns[pk_name].column_name}` = %s"
                with self.db.get_connection().cursor() as cursor:
                    cursor.execute(sql, params)

        instance._is_persisted = True
        instance._original_values = instance.to_dict()

    def _delete_instance(self, instance):
        model = instance.__class__
        pk_name = model._primary_key
        pk_value = getattr(instance, pk_name, None)
        if pk_value is None:
            return

        sql = (
            f"DELETE FROM `{model.__tablename__}` "
            f"WHERE `{model._columns[pk_name].column_name}` = %s"
        )
        with self.db.get_connection().cursor() as cursor:
            cursor.execute(sql, (pk_value,))

        instance._is_persisted = False
        instance._original_values = None


default_db = RawDatabase()


class FuncProxy:
    def __getattr__(self, name):
        return lambda *args: FunctionExpression(name, *args)


db = default_db
func = FuncProxy()

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Silakan login terlebih dahulu untuk mengakses halaman ini."
login_manager.login_message_category = "warning"

session_ext = FlaskSession()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
bcrypt = Bcrypt()
