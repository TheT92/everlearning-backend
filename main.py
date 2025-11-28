# env\Scripts\activate.bat
# uvicorn main:app --reload

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.auth import verify_password, create_access_token, get_password_hash, get_id_from_token
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, sessionmaker
from app.db import engine
from app.models import Base, TCourse, TProblem

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

class CourseCreate(BaseModel):
    title: str
    content: str
    courseType: int
    categories: str
    
class Pagination(BaseModel):
    page: int
    size: int
    
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def paginate(query: Query, pagination: Pagination):
    total = query.count()
    items = query.offset((pagination.page - 1) * pagination.size).limit(pagination.size).all()
    return {
        "items": items,
        "total": total,
        "page": pagination.page,
        "page_size": pagination.size,
        "total_pages": total // pagination.size + 1
    }
    
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
    checkToken(token)
    with engine.connect() as conn:
        sql = text("select uuid, name from t_problem_category t where t.del_flag = false")
        result = conn.execute(sql)
        rows = [dict(row._mapping) for row in result]
    return {"data": rows}

@app.get("/problem/list")
def get_problems_page(params: Pagination = Depends(), token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    checkToken(token)
    with SessionLocal() as session:
        query = session.query(TProblem).filter(TProblem.del_flag == False).order_by(TProblem.create_time.desc())
        result = paginate(query, params)
    return result

@app.get("/problem/{uuid}")
def get_problem_detail(uuid: str, token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    checkToken(token)
    session = SessionLocal()
    try:
        problem = session.query(TProblem).filter(
            TProblem.uuid == uuid,
            TProblem.del_flag == False
        ).first()
        
        if not problem:
            raise HTTPException(
                status_code=404,
                detail=f"Problem not exist"
            )

        current_id = problem.id
        # query previouse problem
        prev_problem = session.query(TProblem).filter(
            TProblem.id > current_id,
            TProblem.del_flag == False
        ).order_by(TProblem.id.asc()).first()
        # query next problem
        next_problem = session.query(TProblem).filter(
            TProblem.id < current_id,
            TProblem.del_flag == False
        ).order_by(TProblem.id.desc()).first()
        prev_id = prev_problem.uuid if prev_problem else None
        next_id = next_problem.uuid if next_problem else None
        problem.prev_id = prev_id
        problem.next_id = next_id
        return problem
    finally:
        session.close()

@app.get("/course/list")
def get_courses_page(params: Pagination = Depends(), token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    checkToken(token)
    with SessionLocal() as session:
        query = session.query(TCourse).filter(TCourse.del_flag == False, TCourse.is_published == True).order_by(TCourse.create_time.desc())
        result = paginate(query, params)
    return result

@app.post("/course/add")
def add_course(course: CourseCreate, token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    email = checkToken(token)
    entity = TCourse(
        title = course.title,
        content = course.content,
        course_type = course.courseType,
        categories = course.categories,
        created_by = email,
        is_published = True,
        del_flag = False
    )
    with SessionLocal() as session:
        session.add(entity)
        session.commit()
    return {"message": "Course create successfully!"}
    
@app.get("/course/{uuid}")
def get_course_detail(uuid: str, token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    checkToken(token)
    with SessionLocal() as session:
        course = session.query(TCourse).filter(
            TCourse.uuid == uuid,
            TCourse.del_flag == False,
            TCourse.is_published == True
        ).first()
        if not course:
            raise HTTPException(
                status_code=404,
                detail=f"Problem not exist"
            )
    return course

        
@app.post("/admin/category/add")
def add_category(category: CategoryCreate, token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    # JWT 验证逻辑
    checkToken(token)
    
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
    checkToken(token)
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
def get_problems_page(params: Pagination = Depends(), token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    checkToken(token)
    session = SessionLocal()
    query = session.query(TProblem).filter(TProblem.del_flag == False).order_by(TProblem.create_time.desc())
    result = paginate(query, params)
    return result
