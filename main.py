# env\Scripts\activate.bat
# uvicorn main:app --reload

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.auth import verify_password, create_access_token
from sqlalchemy import text
from app.db import engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 应用启动时执行
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT NOW();"))
            print("Database Connected:", result.fetchone())
    except Exception as e:
        print("Database Connection Failed:", e)

    yield   # ← 等待应用正常运行期间

    # 应用关闭时执行（可选）
    print("Shutting down...")

app = FastAPI(lifespan=lifespan)

class UserLoginModel(BaseModel):
    username: str
    password: str
    
# 模拟用户数据
fake_users_db = {
    "alice": {
        "username": "alice",
        "hashed_password": "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36iPz06b5OMJROfZw0jYPKa"  # hash of "password"
    }
}


@app.get("/")
def read_root():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM test;"))
            rows = [dict(row._mapping) for row in result]  # 注意 _mapping
        return {"message": "Database connected!", "data": rows}
    except Exception as e:
            return {"error": str(e)}

@app.get("/login")
def login():
    return {"message": "Login endpoint"}

@app.post("/login")
def login_user(user: UserLoginModel):
    return {"username": user.username, "password": user.password}

@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = fake_users_db.get(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user["username"]})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me")
def read_users_me(token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    # JWT 验证逻辑
    return {"token": token}
