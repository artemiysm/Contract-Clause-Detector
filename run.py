import sys
import os
from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.config import Config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = create_app(Config)

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5001))
    logger.info(f"Запуск Contract Clause Detector на порту {port}")
    app.run(debug=False, host='0.0.0.0', port=port)