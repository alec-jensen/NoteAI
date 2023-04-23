from datetime import datetime, timedelta
from typing import Annotated
import re

from fastapi import Depends, FastAPI, HTTPException, status, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
import openai
from database import db

# the school blocks openai, so we need to use a proxy
openai.proxy = "socks5://debian-socks5-proxy.at.remote.it:33000"
openai.api_key = "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"

# to get a string like this run:
# openssl rand -hex 32
SECRET_KEY = "cc61a5800af4cfaa3217356b03ffb032ce22a35bd4aadcaa3fba07268bd2788e"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


class User(BaseModel):
    username: str
    email: str | None = None
    full_name: str | None = None
    disabled: bool | None = False


class UserInDB(User):
    hashed_password: str


class SignupBody(User):
    password: str

class NoteBody(BaseModel):
    name: str
    content: str

class RenameNoteBody(BaseModel):
    old_name: str
    new_name: str

class DeleteNoteBody(BaseModel):
    name: str


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI()

origins = [
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


async def get_password_hash(password):
    return pwd_context.hash(password)


async def authenticate_user(username: str, password: str):
    user = await db.get_user_info(username)
    if not user:
        return False
    if not await verify_password(password, user.get("hashed_password")):
        return False
    return user


async def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = await db.get_user_info(token_data.username)
    if user is None:
        raise credentials_exception
    return UserInDB(**user)


async def get_current_active_user(current_user: Annotated[User, Depends(get_current_user)]):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


@app.on_event("startup")
async def startup():
    await db.create_db()


@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = await create_access_token(
        data={"sub": user.get("username")}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/signup")
async def signup(body: SignupBody):
    if await db.is_username_reserved(body.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )
    if await db.user_exists(body.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )
    if await db.email_taken(body.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists",
        )
    if not re.match(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b', body.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email",
        )

    await db.create_user(body.username, body.email, body.full_name, await get_password_hash(body.password))

    user = await authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = await create_access_token(
        data={"sub": user.get("username")}, expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/users/me/", response_model=User)
async def read_users_me(current_user: Annotated[User, Depends(get_current_active_user)]):
    return current_user


@app.get("/users/me/notes/get")
async def read_own_items(current_user: Annotated[User, Depends(get_current_active_user)]):
    return await db.get_notes(current_user.username)

@app.post("/users/me/notes/add")
async def add_note(current_user: Annotated[User, Depends(get_current_active_user)], body: NoteBody):
    if await db.note_exists(current_user.username, body.name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Note already exists",
        )
    else:
        await db.create_note(current_user.username, body.name, body.content)
    return {"message": "Note added successfully"}

@app.post("/users/me/notes/edit")
async def edit_note(current_user: Annotated[User, Depends(get_current_active_user)], body: NoteBody):
    if await db.note_exists(current_user.username, body.name):
        await db.update_note(current_user.username, body.name, body.content)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Note does not exist",
        )
    return {"message": "Note edited successfully"}

@app.post("/users/me/notes/rename")
async def rename_note(current_user: Annotated[User, Depends(get_current_active_user)], body: RenameNoteBody):
    if await db.note_exists(current_user.username, body.old_name):
        await db.rename_note(current_user.username, body.old_name, body.new_name)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Note does not exist",
        )
    return {"message": "Note renamed successfully"}

@app.post("/users/me/notes/delete")
async def delete_note(current_user: Annotated[User, Depends(get_current_active_user)], body: DeleteNoteBody):
    if await db.note_exists(current_user.username, body.name):
        await db.delete_note(current_user.username, body.name)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Note does not exist",
        )
    return {"message": "Note deleted successfully"}


@app.get("/generate")
async def generate(current_user: Annotated[User, Depends(get_current_active_user)], note: str, num_questions: int = 2):
    questions = []
    if not await db.note_exists(current_user.username, note):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Note does not exist",
        )
    notes = await db.get_notes(current_user.username)
    for _ in range(num_questions):
        res = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            max_tokens=100,
            messages=[
                {"role": "system", "content": "Using the following notes, generate a practice question relevant to the notes."},
                {"role": "user", "content": notes[note]},
            ]
        )
        questions.append(res.choices[0]['message']['content'])

    return {"questions": questions}

@app.get("/answer")
async def answer(current_user: Annotated[User, Depends(get_current_active_user)], question: str, answer: str):
    res = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            max_tokens=100,
            temperature=0.5,
            messages=[
                {"role": "system", "content": "Say whether the following answer is correct or incorrect. If incorrect, briefly explain why."},
                {"role": "assistant", "content": f"Question: {question}"},
                {"role": "system", "content": f"Answer: {answer}"},
            ]
        )
    
    return {"answer": res.choices[0]['message']['content']}
