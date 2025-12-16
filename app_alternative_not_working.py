from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS

import io
import os

from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject, ContentStream, NameObject
from pypdf import Transformation

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# Configurazione (in punti PDF, 72 pt = 1 inch)
# Coordinate in basso a sinistra (sistema PDF standard)
CROP_BOX = (55, 453, 160, 740)  # (x0, y0, x1, y1) in coordinate PDF
PDF_WIDTH = 612
PDF_HEIGHT = 792
GRID_COLS = 5
GRID_ROWS = 2
MARGIN = 20


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/api/process-pdfs', methods=['POST'])
def process_pdfs():
    try:
        files = request.files.getlist('files')
        if not files or len(files) == 0:
            return jsonify({'error': 'Nessun file fornito'}), 400
        if len(files) > 10:
            return jsonify({'error': 'Massimo 10 file consentiti'}), 400

        # Validazione: tutti devono essere PDF
        for file in files:
            if file.filename == '' or not file.filename.lower().endswith('.pdf'):
                return jsonify({'error': f'File non valido: {file.filename}'}), 400

        # Leggi e ritaglia le pagine in coordinate PDF
        cropped_pages = []
        for file in files:
            pdf_bytes = file.read()
            try:
                reader = PdfReader(io.BytesIO(pdf_bytes))
                if len(reader.pages) == 0:
                    continue

                page = reader.pages[0]

                # Imposta una crop box sulla pagina originale
                x0, y0, x1, y1 = CROP_BOX
                crop_rect = RectangleObject([x0, y0, x1, y1])

                page.cropbox = crop_rect

                cropped_pages.append(page)
                print(f"✓ Pagina ritagliata: cropbox={page.cropbox}")
            except Exception as e:
                print(f"❌ Errore PDF: {str(e)}")
                return jsonify({'error': f'Errore elaborazione PDF: {str(e)}'}), 400

        print(f"✓ Totale ritagli: {len(cropped_pages)}")

        # Crea il PDF di output con la griglia
        output_pdf = create_grid_pdf_from_pages(cropped_pages)

        return send_file(
            output_pdf,
            mimetype='application/pdf',
            as_attachment=True,
            download_name='output.pdf'
        )

    except Exception as e:
        print(f"❌ Errore generale: {str(e)}")
        return jsonify({'error': str(e)}), 500


def create_grid_pdf_from_pages(pages):
    """
    Crea un PDF con le pagine ritagliate (cropbox) disposte in una
    griglia GRID_COLS x GRID_ROWS usando form XObject.
    """
    writer = PdfWriter()

    # Calcolo celle in punti
    available_width = PDF_WIDTH - (2 * MARGIN)
    available_height = PDF_HEIGHT - (2 * MARGIN)
    cell_width = available_width / GRID_COLS
    cell_height = available_height / GRID_ROWS

    print(f"Grid: {cell_width} x {cell_height} punti per cella")

    # Crea una pagina base
    base_page = writer.add_blank_page(width=PDF_WIDTH, height=PDF_HEIGHT)

    # Itera sulle celle e piazza i ritagli come form XObject
    for idx, src_page in enumerate(pages):
        if idx >= GRID_COLS * GRID_ROWS:
            break

        row = idx // GRID_COLS
        col = idx % GRID_COLS

        # posizione angolo inferiore della cella
        cell_x = MARGIN + col * cell_width
        cell_y = MARGIN + (GRID_ROWS - 1 - row) * cell_height

        print(f"Ritaglio {idx}: row={row}, col={col}, cell=({cell_x}, {cell_y})")

        # Dimensioni del ritaglio da cropbox
        cx0, cy0, cx1, cy1 = src_page.cropbox
        cx0, cy0, cx1, cy1 = float(cx0), float(cy0), float(cx1), float(cy1)
        crop_w = cx1 - cx0
        crop_h = cy1 - cy0

        # Centra il ritaglio nella cella (senza scaling)
        tx = cell_x + (cell_width - crop_w) / 2
        ty = cell_y + (cell_height - crop_h) / 2

        print(f"  crop size={crop_w}x{crop_h}")
        print(f"  posizionato a ({tx},{ty})")

        # Crea una pagina temporanea e ritagliala correttamente
        tmp_writer = PdfWriter()
        tmp_writer.add_page(src_page)
        tmp_buf = io.BytesIO()
        tmp_writer.write(tmp_buf)
        tmp_buf.seek(0)
        tmp_reader = PdfReader(tmp_buf)
        tmp_page = tmp_reader.pages[0]

        # Reset mediabox a cropbox per visualizzare solo il ritaglio
        tmp_page.mediabox = tmp_page.cropbox

        # Trasforma: trasla per posizionare nella cella
        t = Transformation().translate(tx=tx - cx0, ty=ty - cy0)
        tmp_page.add_transformation(t)
        
        # Merge sulla pagina base
        base_page.merge_page(tmp_page)

    # Scrivi su BytesIO
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    print("✓ PDF salvato correttamente")

    return output


if __name__ == '__main__':
    app.run(debug=True, port=5000)
