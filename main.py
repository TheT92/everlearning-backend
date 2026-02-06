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
from app.models import Base, TCourse, TProblem, TFlashcardReview, TUserFavorite

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


class ReviewRecord(BaseModel):
    """闪卡复习记录：记住了=True, 没记住=False"""
    problemUuid: str
    remembered: bool


class FavoriteAdd(BaseModel):
    problemUuid: str


class ProfileUpdate(BaseModel):
    username: str

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


@app.post("/logout")
def logout():
    """登出（客户端清除 token，此接口用于配合前端拦截器）"""
    return {"message": "Logged out"}


@app.get("/users/me")
def get_user_profile(token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    """获取当前用户资料"""
    email = checkToken(token)
    with engine.connect() as conn:
        sql = text("SELECT username, email FROM t_user WHERE email = :email AND del_flag = false")
        result = conn.execute(sql, {"email": email})
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        return {"data": dict(row._mapping)}


@app.put("/users/me")
def update_user_profile(profile: ProfileUpdate, token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    """更新当前用户资料（用户名）"""
    email = checkToken(token)
    with engine.connect() as conn:
        sql = text("UPDATE t_user SET username = :username WHERE email = :email AND del_flag = false")
        conn.execute(sql, {"username": profile.username, "email": email})
        conn.commit()
    return {"message": "Profile updated"}

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


@app.post("/review/record")
def record_review(record: ReviewRecord, token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    """记录闪卡复习结果：记住了或没记住"""
    email = checkToken(token)
    with engine.connect() as conn:
        sql = text("""
            INSERT INTO t_flashcard_review (user_email, problem_uuid, remembered)
            VALUES (:user_email, :problem_uuid, :remembered)
            ON CONFLICT (user_email, problem_uuid)
            DO UPDATE SET remembered = EXCLUDED.remembered, create_time = NOW()
        """)
        conn.execute(sql, {
            "user_email": email,
            "problem_uuid": record.problemUuid,
            "remembered": record.remembered,
        })
        conn.commit()
    return {"message": "Review recorded"}


@app.get("/review/status")
def get_review_status(token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    """获取当前用户所有题目的复习状态 { problemUuid: remembered }"""
    email = checkToken(token)
    with engine.connect() as conn:
        sql = text("""
            SELECT problem_uuid, remembered
            FROM t_flashcard_review
            WHERE user_email = :user_email
        """)
        result = conn.execute(sql, {"user_email": email})
        rows = [dict(row._mapping) for row in result]
    status = {str(r["problem_uuid"]): r["remembered"] for r in rows}
    return {"data": status}


@app.get("/user/favorites")
def get_user_favorites(
    page: int = 1,
    pageSize: int = 10,
    token: str = Depends(OAuth2PasswordBearer(tokenUrl="token")),
):
    """获取当前用户收藏的题目列表（分页）"""
    email = checkToken(token)
    offset = (page - 1) * pageSize
    with engine.connect() as conn:
        count_sql = text("""
            SELECT COUNT(*) FROM t_user_favorite f
            JOIN t_problem p ON f.problem_uuid = p.uuid::text AND p.del_flag = false
            WHERE f.user_email = :email
        """)
        total = conn.execute(count_sql, {"email": email}).scalar() or 0
        list_sql = text("""
            SELECT p.uuid::text as uuid, p.title, p.create_time
            FROM t_user_favorite f
            JOIN t_problem p ON f.problem_uuid = p.uuid::text AND p.del_flag = false
            WHERE f.user_email = :email
            ORDER BY f.create_time DESC
            LIMIT :limit OFFSET :offset
        """)
        result = conn.execute(list_sql, {"email": email, "limit": pageSize, "offset": offset})
        rows = [dict(row._mapping) for row in result]
    return {"data": {"list": rows, "total": total}}


@app.post("/user/favorites")
def add_favorite(body: FavoriteAdd, token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    """添加收藏"""
    email = checkToken(token)
    with engine.connect() as conn:
        sql = text("""
            INSERT INTO t_user_favorite (user_email, problem_uuid)
            VALUES (:email, :problem_uuid)
            ON CONFLICT (user_email, problem_uuid) DO NOTHING
        """)
        conn.execute(sql, {"email": email, "problem_uuid": body.problemUuid})
        conn.commit()
    return {"message": "Favorite added"}


@app.delete("/user/favorites/{problem_uuid}")
def remove_favorite(
    problem_uuid: str,
    token: str = Depends(OAuth2PasswordBearer(tokenUrl="token")),
):
    """取消收藏"""
    email = checkToken(token)
    with engine.connect() as conn:
        sql = text(
            "DELETE FROM t_user_favorite WHERE user_email = :email AND problem_uuid = :problem_uuid"
        )
        conn.execute(sql, {"email": email, "problem_uuid": problem_uuid})
        conn.commit()
    return {"message": "Favorite removed"}


class FavoriteToggle(BaseModel):
    problemUuid: str
    favorite: bool


@app.get("/favorite/status")
def get_favorite_status(token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    """获取当前用户对所有题目的收藏状态 { problemUuid: true }"""
    email = checkToken(token)
    with engine.connect() as conn:
        sql = text(
            "SELECT problem_uuid FROM t_user_favorite WHERE user_email = :email"
        )
        result = conn.execute(sql, {"email": email})
        rows = [row[0] for row in result]
    status = {str(uuid): True for uuid in rows}
    return {"data": status}


@app.post("/favorite/toggle")
def toggle_favorite(body: FavoriteToggle, token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    """切换收藏状态"""
    email = checkToken(token)
    with engine.connect() as conn:
        if body.favorite:
            sql = text("""
                INSERT INTO t_user_favorite (user_email, problem_uuid)
                VALUES (:email, :problem_uuid)
                ON CONFLICT (user_email, problem_uuid) DO NOTHING
            """)
            conn.execute(sql, {"email": email, "problem_uuid": body.problemUuid})
        else:
            sql = text(
                "DELETE FROM t_user_favorite WHERE user_email = :email AND problem_uuid = :problem_uuid"
            )
            conn.execute(sql, {"email": email, "problem_uuid": body.problemUuid})
        conn.commit()
    return {"message": "Favorite toggled"}


@app.get("/user/stats")
def get_user_stats(token: str = Depends(OAuth2PasswordBearer(tokenUrl="token"))):
    """
    获取当前用户学习统计
    difficulty: 1=Easy, 2=Middle, 3=Hard
    """
    email = checkToken(token)
    with engine.connect() as conn:
        # 各难度已复习数 / 该难度总题数
        stats_sql = text("""
            WITH total_by_diff AS (
                SELECT difficulty, COUNT(*) AS total
                FROM t_problem WHERE del_flag = false GROUP BY difficulty
            ),
            reviewed_by_diff AS (
                SELECT p.difficulty, COUNT(DISTINCT r.problem_uuid) AS reviewed
                FROM t_flashcard_review r
                JOIN t_problem p ON r.problem_uuid = p.uuid::text AND p.del_flag = false
                WHERE r.user_email = :email
                GROUP BY p.difficulty
            )
            SELECT
                COALESCE(t.difficulty, r.difficulty) AS difficulty,
                COALESCE(t.total, 0)::int AS total,
                COALESCE(r.reviewed, 0)::int AS reviewed
            FROM total_by_diff t
            FULL OUTER JOIN reviewed_by_diff r ON t.difficulty = r.difficulty
        """)
        rows = [dict(row._mapping) for row in conn.execute(stats_sql, {"email": email})]
        # 总复习题数（去重）
        solved_sql = text(
            "SELECT COUNT(DISTINCT problem_uuid) FROM t_flashcard_review WHERE user_email = :email"
        )
        problems_solved = conn.execute(solved_sql, {"email": email}).scalar() or 0
    # 构建难度映射 1=Easy, 2=Middle, 3=Hard
    diff_map = {1: "easy", 2: "middle", 3: "hard"}
    stats = {}
    for r in rows:
        d = r.get("difficulty") or 1
        key = diff_map.get(d, "easy")
        stats[key] = {"total": r.get("total", 0), "reviewed": r.get("reviewed", 0)}
    for k in ["easy", "middle", "hard"]:
        if k not in stats:
            stats[k] = {"total": 0, "reviewed": 0}
    return {"data": {"byDifficulty": stats, "problemsSolved": problems_solved}}


@app.get("/user/activities")
def get_user_activities(
    limit: int = 10,
    token: str = Depends(OAuth2PasswordBearer(tokenUrl="token")),
):
    """获取最近复习活动"""
    email = checkToken(token)
    with engine.connect() as conn:
        sql = text("""
            SELECT r.problem_uuid, r.remembered, r.create_time, p.title
            FROM t_flashcard_review r
            JOIN t_problem p ON r.problem_uuid = p.uuid::text AND p.del_flag = false
            WHERE r.user_email = :email
            ORDER BY r.create_time DESC
            LIMIT :limit
        """)
        result = conn.execute(sql, {"email": email, "limit": limit})
        rows = [dict(row._mapping) for row in result]
    return {"data": rows}


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
def get_admin_category_list(
    page: int = 1,
    size: int = 10,
    token: str = Depends(OAuth2PasswordBearer(tokenUrl="token")),
):
    checkToken(token)
    offset = (page - 1) * size
    with engine.connect() as conn:
        count_sql = text("SELECT COUNT(*) FROM t_problem_category WHERE del_flag = false")
        total = conn.execute(count_sql).scalar() or 0
        list_sql = text("""
            SELECT uuid, name FROM t_problem_category
            WHERE del_flag = false
            ORDER BY create_time DESC
            LIMIT :limit OFFSET :offset
        """)
        result = conn.execute(list_sql, {"limit": size, "offset": offset})
        rows = [dict(row._mapping) for row in result]
    return {"list": rows, "total": total}

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
