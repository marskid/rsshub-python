import warnings
# Suppress pkg_resources deprecation warning from Flask 2.0.2
warnings.filterwarnings("ignore", category=UserWarning, module="flask.cli")

import os
import threading
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

from rsshub import create_app

# Use development config for local development
config_name = os.getenv('FLASK_CONFIG', 'development' if os.getenv('FLASK_ENV') == 'development' else 'production')
app = create_app(config_name) 

def warmup():
    try:
        with app.app_context():
            # 创建请求
            with app.test_request_context(path='/newsnow/ai'):
                # 让 Flask 路由系统自动调用
                response = app.dispatch_request()
    except Exception as e:
        print(f"[SWR] Preload failed: {e}")

# threading.Thread(target=warmup, daemon=True).start()
# Standard WSGI application for Vercel
application = app

# For local development
if __name__ == '__main__':
    app.run(debug=False, port=5000)