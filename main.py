# env\Scripts\activate.bat
# uvicorn main:app --reload

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.auth import verify_password, create_access_token, get_password_hash, get_id_from_token
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.db import engine
from app.models import Base  # 假设模型放 models.py

import uuid
import datetime

class UserSignupModel(BaseModel):
    email: str
    username: str
    password: str
    
class UserLoginModel(BaseModel):
    email: str
    password: str
    
class CategoryCreate(BaseModel):
    name: str

class ProblemCreate(BaseModel):
    title: str
    description: str
    problemType: int
    difficulty: int
    categories: str
    answer: str
    
    
def checkToken(token: str) -> str:
    email = get_id_from_token(token)
    if email is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return email

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 应用启动时执行
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT NOW();"))
            print("Database Connected:", result.fetchone())
            Base.metadata.create_all(bind=engine)
    except Exception as e:
        print("Database Connection Failed:", e)

    yield   # ← 等待应用正常运行期间

    # 应用关闭时执行（可选）
    print("Shutting down...")

app = FastAPI(lifespan=lifespan)

@app.get("/")
def read_root():
    with engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM test;"))
            rows = [dict(row._mapping) for row in result]  # 注意 _mapping
    return {"message": "Database connected!", "data": rows}
        
@app.post("/signup")
def login_user(user: UserSignupModel):
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


@app.post("/login")
def login_user(user: UserLoginModel):
    with engine.connect() as conn:
        sql = text("select * from t_user t where t.email = :email")
        result = conn.execute(sql, { "email": user.email })
        rows = [dict(row._mapping) for row in result]
        if len(rows) <= 0:
            raise HTTPException(status_code=400, detail="Incorrect username or password")
        if not verify_password(user.password, rows[0].get('password')):
            raise HTTPException(status_code=400, detail="Incorrect username or password")
        
    access_token = create_access_token(data={"sub": rows[0].get('email')})
    return {"token": access_token}

@app.get("/users/me")
def read_users_me(token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    # JWT 验证逻辑
    return {"token": token}

@app.get("/category/list")
def get_categories(token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    # JWT 验证逻辑
    email = get_id_from_token(token)
    with engine.connect() as conn:
        sql = text("select uuid, name from t_problem_category t where t.del_flag = false")
        result = conn.execute(sql)
        rows = [dict(row._mapping) for row in result]
    return {"data": rows}

@app.post("/admin/category/add")
def add_category(category: CategoryCreate, token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    # JWT 验证逻辑
    email = get_id_from_token(token)
    
    try:
        with engine.connect() as conn:
            # 生成 UUID
            category_uuid = str(uuid.uuid4())
            
            # 构建 SQL 语句
            sql = text("""
                INSERT INTO t_problem_category (uuid, name, del_flag) 
                VALUES (:uuid, :name, :del_flag)
            """)
            # 执行插入操作
            result = conn.execute(sql, {
                'uuid': category_uuid,
                'name': category.name,
                'del_flag': False  # 默认值，表示未删除
            })
            
            # 提交事务
            conn.commit()
    except IntegrityError as e:
        # 判断是否是唯一约束（也可以直接返回）
        if "unique" in str(e.orig).lower():
            raise HTTPException(status_code=400, detail="Category name already exists")
        else:
            raise HTTPException(status_code=500, detail="Database error")
        
    return {"message": "Category create successfully!"}

@app.get("/admin/category/list")
def get_categories(token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    # JWT 验证逻辑
    email = get_id_from_token(token)
    with engine.connect() as conn:
        sql = text("select uuid, name from t_problem_category t where t.del_flag = false")
        result = conn.execute(sql)
        rows = [dict(row._mapping) for row in result]
        
    return {"data": rows}

@app.post("/admin/problem/add")
def add_problem(problem: ProblemCreate, token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    # JWT 验证逻辑
    email = checkToken(token)
    
    try:
        with engine.connect() as conn:
            sql = text("""
                INSERT INTO t_problem (uuid, title, description, problem_type, difficulty, categories, answer, created_by, del_flag) 
                VALUES (:uuid, :title, :description, :problem_type, :difficulty, :categories, :answer, :created_by, :del_flag)
            """)
            problem_uuid = str(uuid.uuid4())
            result = conn.execute(sql, {
                'uuid': problem_uuid,
                'title': problem.title,
                'description': problem.description,
                'problem_type': problem.problemType,
                'difficulty': problem.difficulty,
                'categories': problem.categories,
                'answer': problem.answer,
                'created_by': email,
                'del_flag': False
            })
            
            # 提交事务
            conn.commit()
    except IntegrityError as e:
        # 判断是否是唯一约束（也可以直接返回）
        if "unique" in str(e.orig).lower():
            raise HTTPException(status_code=400, detail="Problem title already exists")
        else:
            raise HTTPException(status_code=500, detail="Database error")
        
    return {"message": "Problem create successfully!"}

@app.get("/admin/problem/list")
def get_problems(token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    checkToken(token)
    
    with engine.connect() as conn:
        sql = text("select * from t_problem t where t.del_flag = false")
        result = conn.execute(sql)
        rows = [dict(row._mapping) for row in result]
        
    return {"data": rows}
