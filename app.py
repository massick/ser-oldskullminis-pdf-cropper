from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from pdf2image import convert_from_bytes
from PIL import Image
import io
import os
import tempfile
import shutil
from reportlab.pdfgen import canvas

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# Configurazione
CROP_BOX = (55, 52, 160, 339)  # (x0, y0, x1, y1)
PDF_WIDTH = 612
PDF_HEIGHT = 792
GRID_COLS = 5
GRID_ROWS = 2
MARGIN = 20
DPI = 300

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

        # Ritagliare le illustrazioni da ogni PDF
        images = []
        for file in files:
            pdf_bytes = file.read()
            try:
                # Convertire PDF a immagine (prima pagina)
                images_list = convert_from_bytes(
                    pdf_bytes,
                    dpi=DPI,
                    first_page=1,
                    last_page=1
                )

                if images_list:
                    img = images_list[0]

                    # Calcolare scaling factor (da punti a pixel)
                    # PDF standard è 72 DPI, convertiamo a 300 DPI
                    scale = DPI / 72.0

                    # Ritagliare l'area specificata (in punti)
                    x0, y0, x1, y1 = CROP_BOX

                    # Convertire coordinate da punti a pixel
                    px0 = int(x0 * scale)
                    py0 = int(y0 * scale)
                    px1 = int(x1 * scale)
                    py1 = int(y1 * scale)

                    # Ritagliare immagine
                    cropped = img.crop((px0, py0, px1, py1))
                    images.append(cropped)
                    print(f"✓ Immagine {len(images)} ritagliata: {cropped.size}")

            except Exception as e:
                print(f"❌ Errore PDF: {str(e)}")
                return jsonify({'error': f'Errore elaborazione PDF: {str(e)}'}), 400

        print(f"✓ Totale immagini: {len(images)}")

        # Creare PDF output con griglia
        output_pdf = create_grid_pdf(images)

        return send_file(
            output_pdf,
            mimetype='application/pdf',
            as_attachment=True,
            download_name='output.pdf'
        )

    except Exception as e:
        print(f"❌ Errore generale: {str(e)}")
        return jsonify({'error': str(e)}), 500

def create_grid_pdf(images):
    """Crea un PDF con le immagini in griglia 5x2 centrate"""

    # Parametri griglia
    grid_cols = 5
    grid_rows = 2
    margin = 20  # punti

    # Calcolatura dimensioni celle
    available_width = PDF_WIDTH - (2 * margin)
    available_height = PDF_HEIGHT - (2 * margin)

    cell_width = available_width / grid_cols
    cell_height = available_height / grid_rows

    print(f"Grid: {cell_width} x {cell_height} punti per cella")

    # Creare buffer PDF
    output = io.BytesIO()
    c = canvas.Canvas(output, pagesize=(PDF_WIDTH, PDF_HEIGHT))

    # Creare cartella temporanea per immagini
    temp_dir = tempfile.mkdtemp()

    try:
        # Iterare sulle celle della griglia
        for idx, img in enumerate(images):
            if idx >= (grid_rows * grid_cols):
                break

            row = idx // grid_cols
            col = idx % grid_cols

            # Calcolare posizione della cella (dall'alto verso il basso)
            x = margin + (col * cell_width)
            y = PDF_HEIGHT - margin - ((row + 1) * cell_height)

            print(f"Immagine {idx}: row={row}, col={col}, x={x}, y={y}")

            # Calcolare dimensioni immagine mantenendo aspect ratio
            img_width, img_height = img.size
            aspect_ratio = img_width / img_height

            # Adattare immagine alla cella
            max_width = cell_width - 4
            max_height = cell_height - 4

            if aspect_ratio > 1:  # Più larga che alta
                img_display_width = min(max_width, max_height * aspect_ratio)
                img_display_height = img_display_width / aspect_ratio
            else:  # Più alta che larga
                img_display_height = min(max_height, max_width / aspect_ratio)
                img_display_width = img_display_height * aspect_ratio

            # Centrare immagine nella cella
            img_x = x + (cell_width - img_display_width) / 2
            img_y = y + (cell_height - img_display_height) / 2

            print(f"  Dimensioni display: {img_display_width} x {img_display_height}")
            print(f"  Posizione: ({img_x}, {img_y})")

            # Salvare immagine temporaneamente su disco
            temp_img_path = os.path.join(temp_dir, f'img_{idx}.png')
            img.save(temp_img_path, format='PNG')

            # Disegnare immagine sul canvas
            c.drawImage(
                temp_img_path,
                img_x,
                img_y,
                width=img_display_width,
                height=img_display_height
            )

        c.save()
        output.seek(0)
        print("✓ PDF salvato correttamente")

    finally:
        # Pulire file temporanei
        shutil.rmtree(temp_dir, ignore_errors=True)

    return output

if __name__ == '__main__':
    app.run(debug=True, port=5000)
