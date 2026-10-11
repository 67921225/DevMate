import os

# 指向 backend 目录的绝对路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WORK_DIR = os.path.join(BASE_DIR, 'workspace')

DATABASE_URL = f"sqlite:///{BASE_DIR}/database.db"