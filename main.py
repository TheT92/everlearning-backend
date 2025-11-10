# env\Scripts\activate.bat
# uvicorn main:app --reload
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class UserLoginModel(BaseModel):
    username: str
    password: str


@app.get("/")
def read_root():
    return {"message": "Hello, World!"}

@app.get("/login")
def login():
    return {"message": "Login endpoint"}

@app.post("/login")
def login_user(user: UserLoginModel):
    return {"username": user.username, "password": user.password}
