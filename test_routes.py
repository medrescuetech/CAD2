from flask import Blueprint, render_template

# Create a blueprint for our test routes
test_bp = Blueprint('test', __name__)

@test_bp.route('/test_frontend')
def test_frontend():
    """
    Route to serve the frontend test page
    """
    return render_template('test_frontend.html')
