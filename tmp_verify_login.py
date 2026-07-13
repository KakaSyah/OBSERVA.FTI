from backend import create_app

app = create_app()
client = app.test_client()
with client.session_transaction() as sess:
    sess['_csrf_token'] = 'test'

resp = client.post(
    '/auth/login',
    data={'nid': 'admin', 'password': 'admin123', 'csrf_token': 'test', 'submit': 'Login'},
    follow_redirects=False,
)
print('LOGIN_STATUS', resp.status_code, resp.headers.get('Location'))
with client.session_transaction() as sess:
    print('SESSION_HAS_USER', '_user_id' in sess)
resp2 = client.get('/admin/dashboard', follow_redirects=False)
print('DASHBOARD_STATUS', resp2.status_code)
print(resp2.data.decode('utf-8', 'ignore')[:200])
