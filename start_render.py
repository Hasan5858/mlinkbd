#!/usr/bin/env python3
"""
Start script for Render deployment
"""

import os
from movielinkbd_api import app

if __name__ == '__main__':
    # Get port from environment variable (Render sets this)
    port = int(os.environ.get('PORT', 5001))
    
    # Run the app
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False  # Disable debug mode for production
    )
