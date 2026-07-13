/* Shared Hybrid PDF engine: image letterhead + vector observation letter text. */
(function (window) {
    "use strict";

    // Semua jarak vertikal surat menggunakan satuan mm agar mudah ditelusuri.
    var LINE_HEIGHT = 5.2;
    var PARAGRAPH_GAP = 4.8;
    var DATE_OFFSET = 3;
    var DATE_BLOCK_HEIGHT = LINE_HEIGHT;
    // Menjaga posisi body lama: 3 + 5.2 + 25 = 33.2 mm dari akhir metadata.
    var SECTION_GAP = 25;
    var SIGNATURE_NAME_OFFSET = 21;
    var SIGNATURE_LINE_GAP = 1;
    var SIGNATURE_ROLE_GAP = 5;
    var SIGNATURE_BOTTOM_GAP = 4;
    // Ukuran & posisi gambar tanda tangan digital, diukur dari PDF referensi (Alur 2 - Kirim TTD Digital):
    // kotak ~30.7mm x ~24mm, mulai tepat di bawah label "Mengetahui"/"Menyetujui",
    // berakhir sedikit melewati garis TTD, center-nya sejajar dengan leftCenter/rightCenter.
    var SIGNATURE_IMAGE_WIDTH = 30;
    var SIGNATURE_IMAGE_BOTTOM_PAD = 2;

    function blobToDataUrl(blob) {
        return new Promise(function (resolve, reject) {
            var reader = new FileReader();
            reader.onload = function () { resolve(reader.result); };
            reader.onerror = function () { reject(new Error("Gagal membaca background kop surat.")); };
            reader.readAsDataURL(blob);
        });
    }

    function loadImage(url) {
        return new Promise(function (resolve, reject) {
            var image = new Image();
            image.crossOrigin = "anonymous";
            image.onload = function () { resolve(image); };
            image.onerror = function () { reject(new Error("Background kop surat tidak dapat dimuat untuk PDF.")); };
            image.src = url;
        });
    }

    async function pngHasAlpha(blob) {
        var bytes = new Uint8Array(await blob.arrayBuffer());
        var signature = [137, 80, 78, 71, 13, 10, 26, 10];
        if (!signature.every(function (value, index) { return bytes[index] === value; })) return false;
        var offset = 8;
        var colorType = null;
        while (offset + 12 <= bytes.length) {
            var length = (((bytes[offset] << 24) >>> 0) | (bytes[offset + 1] << 16) | (bytes[offset + 2] << 8) | bytes[offset + 3]);
            var type = String.fromCharCode.apply(null, bytes.slice(offset + 4, offset + 8));
            if (type === "IHDR") colorType = bytes[offset + 17];
            if (type === "tRNS") return true;
            if (type === "IEND" || offset + length + 12 > bytes.length) break;
            offset += length + 12;
        }
        return colorType === 4 || colorType === 6;
    }

    function canvasToBlob(canvas, type, quality) {
        return new Promise(function (resolve, reject) {
            canvas.toBlob(function (blob) {
                if (blob) resolve(blob);
                else reject(new Error("Gagal menyiapkan background kop surat untuk PDF."));
            }, type, quality);
        });
    }

    function flattenToWhite(image) {
        var canvas = document.createElement("canvas");
        canvas.width = image.naturalWidth;
        canvas.height = image.naturalHeight;
        var context = canvas.getContext("2d", { alpha: false });
        context.fillStyle = "#ffffff";
        context.fillRect(0, 0, canvas.width, canvas.height);
        context.drawImage(image, 0, 0, canvas.width, canvas.height);
        return canvas;
    }

    async function drawLetterheadBackground(pdf, backgroundUrl) {
        if (!backgroundUrl) return;
        var image = await loadImage(backgroundUrl);
        var pageWidth = pdf.internal.pageSize.getWidth();
        var pageHeight = pdf.internal.pageSize.getHeight();
        var scale = Math.max(pageWidth / image.naturalWidth, pageHeight / image.naturalHeight);
        var width = image.naturalWidth * scale;
        var height = image.naturalHeight * scale;
        var canvas = flattenToWhite(image);
        var png = await canvasToBlob(canvas, "image/png");
        var imageData;
        var format;
        if (await pngHasAlpha(png)) {
            imageData = canvas.toDataURL("image/jpeg", 0.98);
            format = "JPEG";
        } else {
            imageData = await blobToDataUrl(png);
            format = "PNG";
        }
        pdf.addImage(imageData, format, (pageWidth - width) / 2, (pageHeight - height) / 2, width, height, undefined, "SLOW");
    }

    function layoutFor(pdf, setting) {
        var topMargin = Number(setting.top) || 20;
        var headerHeight = Number(setting.headerHeight) || 0;
        var margins = { top: Math.max(topMargin, headerHeight), right: Number(setting.right) || 20, bottom: Number(setting.bottom) || 20, left: Number(setting.left) || 20 };
        var pageWidth = pdf.internal.pageSize.getWidth();
        return Object.assign(margins, { pageWidth: pageWidth, pageHeight: pdf.internal.pageSize.getHeight(), contentWidth: pageWidth - margins.left - margins.right, bottomLimit: pdf.internal.pageSize.getHeight() - margins.bottom });
    }

    function wrapped(pdf, text, x, y, width, options) {
        var lineHeight = (options && options.lineHeight) || LINE_HEIGHT;
        var lines = pdf.splitTextToSize(String(text || ""), width);
        pdf.text(lines, x, y, Object.assign({ baseline: "top" }, options || {}));
        return y + lines.length * lineHeight;
    }

    function drawLetterNumber(pdf, data, layout, subject, y) {
        pdf.setFont("helvetica", "normal"); pdf.setFontSize(10);
        pdf.text("Nomor:", layout.left, y, { baseline: "top" });
        pdf.text(data.documentNumber || "-", layout.left, y + LINE_HEIGHT, { baseline: "top" });
        var subjectLabelY = y + (LINE_HEIGHT * 2);
        pdf.text("Perihal:", layout.left, subjectLabelY, { baseline: "top" });
        return wrapped(pdf, subject, layout.left, subjectLabelY + LINE_HEIGHT, layout.contentWidth * 0.45, { lineHeight: LINE_HEIGHT });
    }

    function drawRecipient(pdf, data, layout, y) {
        var x = layout.left + layout.contentWidth * 0.60, width = layout.pageWidth - layout.right - x;
        pdf.setFont("helvetica", "normal"); pdf.setFontSize(10); pdf.text("Kepada Yth:", x, y, { baseline: "top" });
        y = wrapped(pdf, data.recipient || "-", x, y + LINE_HEIGHT, width, { lineHeight: LINE_HEIGHT });
        y = wrapped(pdf, data.company || "-", x, y, width, { lineHeight: LINE_HEIGHT });
        return wrapped(pdf, data.address || "-", x, y, width, { lineHeight: LINE_HEIGHT });
    }

    function drawBody(pdf, data, layout, y) {
        pdf.setFont("helvetica", "normal"); pdf.setFontSize(10);
        y = wrapped(pdf, "Dengan Hormat,", layout.left, y, layout.contentWidth, { lineHeight: LINE_HEIGHT }) + PARAGRAPH_GAP;
        return wrapped(pdf, "Bersama dengan surat ini kami memberitahukan bahwa mahasiswa Fakultas Teknologi Informasi Program Studi " + (data.studyProgram || "-") + " Universitas Kristen Satya Wacana berikut ini:", layout.left, y, layout.contentWidth, { lineHeight: LINE_HEIGHT }) + PARAGRAPH_GAP;
    }

    function drawMembers(pdf, data, layout, y) {
        var members = Array.isArray(data.members) ? data.members : [], nameX = layout.left + 8, nimX = layout.left + layout.contentWidth - 34, nameWidth = nimX - nameX - 4;
        pdf.setFont("helvetica", "normal"); pdf.setFontSize(10);
        members.forEach(function (member, index) {
            var lines = pdf.splitTextToSize(member.name || "-", nameWidth);
            pdf.text((index + 1) + ".", layout.left, y, { baseline: "top" }); pdf.text(lines, nameX, y, { baseline: "top" }); pdf.text(member.nim || "-", nimX, y, { baseline: "top" });
            y += Math.max(1, lines.length) * LINE_HEIGHT;
        });
        return y + PARAGRAPH_GAP;
    }

    function drawClosing(pdf, data, layout, y) {
        y = wrapped(pdf, "Bahwa sebagai salah satu syarat untuk memenuhi sebagian tugas dari mata kuliah " + (data.course || "-") + ", maka melalui surat ini kami mohon kesediaan Bapak/Ibu untuk memberikan izin kepada mahasiswa yang bersangkutan di " + (data.company || "-") + ".", layout.left, y, layout.contentWidth, { lineHeight: LINE_HEIGHT }) + PARAGRAPH_GAP;
        y = wrapped(pdf, "Demikian surat ini kami sampaikan. Atas perhatian dan izin yang diberikan diucapkan terima kasih.", layout.left, y, layout.contentWidth, { lineHeight: LINE_HEIGHT }) + PARAGRAPH_GAP;
        return wrapped(pdf, "Salam,", layout.left, y, layout.contentWidth, { lineHeight: LINE_HEIGHT });
    }

    /** Menghitung tinggi blok TTD berdasarkan jumlah baris nama terpanjang. */
    function getSignatureMetrics(pdf, data, columnWidth) {
        pdf.setFont("helvetica", "bold");
        pdf.setFontSize(10);
        var headLines = pdf.splitTextToSize(data.headOfProgram || "-", columnWidth);
        var lecturerLines = pdf.splitTextToSize(data.lecturer || "-", columnWidth);
        var nameLineCount = Math.max(headLines.length, lecturerLines.length, 1);
        var nameY = SIGNATURE_NAME_OFFSET;
        var lineY = nameY + (nameLineCount * LINE_HEIGHT) + SIGNATURE_LINE_GAP;
        var roleY = lineY + SIGNATURE_ROLE_GAP;
        return {
            headLines: headLines,
            lecturerLines: lecturerLines,
            nameY: nameY,
            lineY: lineY,
            roleY: roleY,
            // SIGNATURE_BLOCK_HEIGHT dinamis agar clamp aman untuk nama multi-baris.
            height: roleY + LINE_HEIGHT + SIGNATURE_BOTTOM_GAP
        };
    }

    function canvasFromImagePreservingAlpha(image) {
        var canvas = document.createElement("canvas");
        canvas.width = image.naturalWidth;
        canvas.height = image.naturalHeight;
        var context = canvas.getContext("2d");
        context.drawImage(image, 0, 0);
        return canvas;
    }

    /** Muat & gambar satu tanda tangan digital di dalam kotak (centerX, topY, maxWidth, maxHeight). */
    async function drawSignatureImage(pdf, url, centerX, topY, maxWidth, maxHeight, label) {
        if (!url) {
            throw new Error(
                "URL tanda tangan digital (" + label + ") tidak ditemukan. " +
                "Pastikan " + label + " sudah mengunggah tanda tangan lewat menu Admin > Akademik Pengguna."
            );
        }
        var image = await loadImage(url);
        var canvas = canvasFromImagePreservingAlpha(image);
        var dataUrl = canvas.toDataURL("image/png");
        var scale = Math.min(maxWidth / image.naturalWidth, maxHeight / image.naturalHeight);
        var width = image.naturalWidth * scale;
        var height = image.naturalHeight * scale;
        var x = centerX - width / 2;
        var y = topY + Math.max(0, (maxHeight - height) / 2);
        pdf.addImage(dataUrl, "PNG", x, y, width, height, undefined, "SLOW");
    }

    async function drawSignature(pdf, data, layout, y, metrics, options) {
        var gap = 25, columnWidth = (layout.contentWidth - gap) / 2, leftCenter = layout.left + columnWidth / 2, rightCenter = layout.left + columnWidth + gap + columnWidth / 2;
        metrics = metrics || getSignatureMetrics(pdf, data, columnWidth);
        pdf.setFont("helvetica", "normal"); pdf.setFontSize(10);
        pdf.text("Mengetahui", leftCenter, y, { align: "center", baseline: "top" });
        pdf.text("Menyetujui", rightCenter, y, { align: "center", baseline: "top" });
        pdf.setFont("helvetica", "bold");
        pdf.text(metrics.headLines, leftCenter, y + metrics.nameY, { align: "center", baseline: "top" });
        pdf.text(metrics.lecturerLines, rightCenter, y + metrics.nameY, { align: "center", baseline: "top" });
        pdf.setLineWidth(0.25);
        pdf.line(leftCenter - columnWidth * 0.32, y + metrics.lineY, leftCenter + columnWidth * 0.32, y + metrics.lineY);
        pdf.line(rightCenter - columnWidth * 0.32, y + metrics.lineY, rightCenter + columnWidth * 0.32, y + metrics.lineY);
        pdf.setFont("helvetica", "normal"); pdf.setFontSize(9);
        pdf.text("Kaprodi", leftCenter, y + metrics.roleY, { align: "center", baseline: "top" });
        pdf.text("Pengampu Mata Kuliah", rightCenter, y + metrics.roleY, { align: "center", baseline: "top" });

        // Alur 2 (Kirim TTD Digital) WAJIB ada gambar tanda tangan. Alur 1 (Cetak Hardfile)
        // sengaja tidak memanggil blok ini sama sekali -> area tetap kosong, itu bukan bug.
        if (options && options.digitalSignature) {
            var imgTop = y + LINE_HEIGHT;
            var imgMaxHeight = (metrics.lineY + SIGNATURE_IMAGE_BOTTOM_PAD) - LINE_HEIGHT;
            var imgMaxWidth = Math.min(SIGNATURE_IMAGE_WIDTH, columnWidth * 0.45);
            await drawSignatureImage(pdf, data.headOfProgramSignatureUrl, leftCenter, imgTop, imgMaxWidth, imgMaxHeight, "Kaprodi");
            await drawSignatureImage(pdf, data.lecturerSignatureUrl, rightCenter, imgTop, imgMaxWidth, imgMaxHeight, "Dosen Pengampu");
        }
    }

    async function buildObservationPdf(data, options) {
        if (!window.jspdf) throw new Error("Pembuat PDF tidak tersedia. Muat ulang halaman lalu coba kembali.");
        options = options || {};
        var pdf = new window.jspdf.jsPDF({ orientation: "portrait", unit: "mm", format: "a4", compress: true });
        var layout = layoutFor(pdf, options.kopSetting || {});
        await drawLetterheadBackground(pdf, (options.kopSetting || {}).backgroundUrl);
        var metaBottom = Math.max(drawLetterNumber(pdf, data, layout, options.subject || "", layout.top), drawRecipient(pdf, data, layout, layout.top));
        pdf.setFont("helvetica", "normal"); pdf.setFontSize(9.5);
        pdf.text(data.date || "-", layout.pageWidth - layout.right, metaBottom + DATE_OFFSET, { align: "right", baseline: "top" });
        var y = drawBody(pdf, data, layout, metaBottom + DATE_OFFSET + DATE_BLOCK_HEIGHT + SECTION_GAP);
        if (y > layout.bottomLimit) {
            pdf.addPage();
            y = layout.top;
        }
        y = drawMembers(pdf, data, layout, y);
        if (y > layout.bottomLimit) {
            pdf.addPage();
            y = layout.top;
        }
        y = drawClosing(pdf, data, layout, y);
        var signatureColumnWidth = (layout.contentWidth - 25) / 2;
        var signatureMetrics = getSignatureMetrics(pdf, data, signatureColumnWidth);
        var SIGNATURE_BLOCK_HEIGHT = signatureMetrics.height;
        if (y + PARAGRAPH_GAP + SIGNATURE_BLOCK_HEIGHT > layout.bottomLimit) {
            pdf.addPage();
            y = layout.top;
        }
        await drawSignature(pdf, data, layout, Math.min(y + PARAGRAPH_GAP, layout.bottomLimit - SIGNATURE_BLOCK_HEIGHT), signatureMetrics, options);
        return pdf.output("blob");
    }

    window.ObservationPdf = { buildObservationPdf: buildObservationPdf };
})(window);
