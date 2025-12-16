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

# Configuration
CROP_BOX = (55, 52, 160, 339)  # (x0, y0, x1, y1) in PDF points
PDF_WIDTH = 612
PDF_HEIGHT = 792
GRID_COLS = 5
GRID_ROWS = 2
DPI = 300

# Page margins (matching original PDF layout)
LEFT_MARGIN = 55
RIGHT_MARGIN = 55
TOP_MARGIN = 52
BOTTOM_MARGIN = 52

# Measured scale fix
SCALE_FIX = 1.04


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/api/process-pdfs', methods=['POST'])
def process_pdfs():
    try:
        files = request.files.getlist('files')
        if not files or len(files) == 0:
            return jsonify({'error': 'No files provided'}), 400
        if len(files) > 10:
            return jsonify({'error': 'Maximum 10 files allowed'}), 400

        # Validation: all files must be PDFs
        for file in files:
            if file.filename == '' or not file.filename.lower().endswith('.pdf'):
                return jsonify({'error': f'Invalid file: {file.filename}'}), 400

        # Crop illustrations from each PDF
        images = []
        for file in files:
            pdf_bytes = file.read()
            try:
                # Convert first page of PDF to image
                images_list = convert_from_bytes(
                    pdf_bytes,
                    dpi=DPI,
                    first_page=1,
                    last_page=1
                )

                if images_list:
                    img = images_list[0]

                    # Compute scaling factor (PDF points -> pixels)
                    # Standard PDF is 72 DPI, convert to configured DPI
                    scale = DPI / 72.0

                    # Crop the specified area (in PDF points)
                    x0, y0, x1, y1 = CROP_BOX

                    # Convert coordinates from points to pixels
                    px0 = int(x0 * scale)
                    py0 = int(y0 * scale)
                    px1 = int(x1 * scale)
                    py1 = int(y1 * scale)

                    # Crop image
                    cropped = img.crop((px0, py0, px1, py1))
                    images.append(cropped)
                    print(f"✓ Cropped image {len(images)}: {cropped.size}")
            except Exception as e:
                print(f"❌ PDF error: {str(e)}")
                return jsonify({'error': f'Error processing PDF: {str(e)}'}), 400

        print(f"✓ Total cropped images: {len(images)}")

        # Create output PDF with grid
        output_pdf = create_grid_pdf(images)

        return send_file(
            output_pdf,
            mimetype='application/pdf',
            as_attachment=True,
            download_name='output.pdf'
        )

    except Exception as e:
        print(f"❌ General error: {str(e)}")
        return jsonify({'error': str(e)}), 500


def create_grid_pdf(images):
    """
    Create a PDF with the cropped images arranged
    in a 5x2 grid, with page margins matching the original layout.
    """
    grid_cols = GRID_COLS
    grid_rows = GRID_ROWS

    # Usable area for the grid inside page margins
    available_width = PDF_WIDTH - (LEFT_MARGIN + RIGHT_MARGIN)
    available_height = PDF_HEIGHT - (TOP_MARGIN + BOTTOM_MARGIN)

    cell_width = available_width / grid_cols
    cell_height = available_height / grid_rows

    print(f"Grid: {cell_width} x {cell_height} points per cell")

    output = io.BytesIO()
    c = canvas.Canvas(output, pagesize=(PDF_WIDTH, PDF_HEIGHT))

    temp_dir = tempfile.mkdtemp()

    try:
        for idx, img in enumerate(images):
            if idx >= (grid_rows * grid_cols):
                break

            row = idx // grid_cols
            col = idx % grid_cols

            # Cell coordinates (starting from top of page)
            x_cell = LEFT_MARGIN + col * cell_width
            y_cell = PDF_HEIGHT - TOP_MARGIN - (row + 1) * cell_height

            print(f"Image {idx}: row={row}, col={col}, cell=({x_cell}, {y_cell})")

            # Original image size in pixels
            img_width, img_height = img.size
            aspect_ratio = img_width / img_height

            # Cell defines the available space
            max_width = cell_width
            max_height = cell_height

            if aspect_ratio > 1:  # Wider than tall
                img_display_width = min(max_width, max_height * aspect_ratio)
                img_display_height = img_display_width / aspect_ratio
            else:  # Taller than wide
                img_display_height = min(max_height, max_width / aspect_ratio)
                img_display_width = img_display_height * aspect_ratio

            # Apply measured scale fix
            img_display_width *= SCALE_FIX
            img_display_height *= SCALE_FIX

            # Center image inside the cell
            img_x = x_cell + (cell_width - img_display_width) / 2
            img_y = y_cell + (cell_height - img_display_height) / 2

            print(f" Display size: {img_display_width} x {img_display_height}")
            print(f" Position: ({img_x}, {img_y})")

            # Save image temporarily to disk
            temp_img_path = os.path.join(temp_dir, f'img_{idx}.png')
            img.save(temp_img_path, format='PNG')

            # Draw image on the canvas
            c.drawImage(
                temp_img_path,
                img_x,
                img_y,
                width=img_display_width,
                height=img_display_height
            )

        c.save()
        output.seek(0)
        print("✓ Output PDF saved successfully")

    finally:
        # Clean up temporary files
        shutil.rmtree(temp_dir, ignore_errors=True)

    return output


if __name__ == '__main__':
    app.run(debug=True, port=5000)
