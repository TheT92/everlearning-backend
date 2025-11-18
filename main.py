# env\Scripts\activate.bat
# uvicorn main:app --reload

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.auth import verify_password, create_access_token, get_password_hash
from sqlalchemy import text
from app.db import engine

import uuid
import datetime

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

class UserSignupModel(BaseModel):
    email: str
    username: str
    password: str
    
class UserLoginModel(BaseModel):
    email: str
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
        
@app.post("/signup")
def login_user(user: UserSignupModel):
    try:
        with engine.connect() as conn:
            # 生成 UUID
            user_uuid = str(uuid.uuid4())
            
            # 构建 SQL 语句
            sql = text("""
                INSERT INTO t_user (uuid, username, password, email, del_flag) 
                VALUES (:uuid, :username, :password, :email, :del_flag)
            """)
            # 执行插入操作
            result = conn.execute(sql, {
                'uuid': user_uuid,
                'username': user.username,
                'password': get_password_hash(user.password),  # 注意：密码应该先加密再存储

                'email': user.email,
                'del_flag': False  # 默认值，表示未删除
            })
            
            # 提交事务
            conn.commit()
            
        return {"message": "User registered successfully!", "user_id": user_uuid}
    except Exception as e:
            return {"error": str(e)}

@app.post("/login")
def login_user(user: UserLoginModel):
    try:
        with engine.connect() as conn:
            sql = text("select * from t_user t where t.email = :email")
            result = conn.execute(sql, { "email": user.email })
            rows = [dict(row._mapping) for row in result]
            if len(rows) <= 0:
                raise HTTPException(status_code=400, detail="Incorrect username or password")
            if not verify_password(user.password, rows[0].get('password')):
                raise HTTPException(status_code=400, detail="Incorrect username or password")
            
        access_token = create_access_token(data={"sub": rows[0].get('email')})
        return {"token": access_token, "prefix": "Bearer"}
    except Exception as e:
            return {"error": str(e)}

@app.get("/users/me")
def read_users_me(token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    # JWT 验证逻辑
    return {"token": token}
