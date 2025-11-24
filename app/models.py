from sqlalchemy import (
    Column, Integer, Text, Boolean, TIMESTAMP, func, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base
import uuid

Base = declarative_base()

class TUser(Base):
    __tablename__ = "t_user"
    __table_args__ = (
        UniqueConstraint("email", name="t_user_email_key"),
        UniqueConstraint("uuid", name="t_user_uuid_key"),
    )

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    uuid = Column(
        UUID(as_uuid=True),
        nullable=False,
        default=uuid.uuid4   # 让 SQLAlchemy 自动生成 uuid
    )

    username = Column(Text, nullable=False)

    password = Column(Text, nullable=False)

    create_time = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now()
    )

    email = Column(Text, nullable=False)

    del_flag = Column(
        Boolean,
        server_default="false",
        nullable=True
    )


class TProblemCategory(Base):
    __tablename__ = "t_problem_category"
    __table_args__ = (
        UniqueConstraint("name", name="t_category_name_key"),
        UniqueConstraint("uuid", name="t_category_uuid_key"),
    )
    
    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    uuid = Column(
        UUID(as_uuid=True),
        nullable=False,
        default=uuid.uuid4   # 让 SQLAlchemy 自动生成 uuid
    )
    
    name = Column(Text, nullable=False)
    
    create_time = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now()
    )
    
    del_flag = Column(
        Boolean,
        server_default="false",
        nullable=True
    )
    
class TProblem(Base):
    __tablename__ = "t_problem"
    __table_args__ = (
        UniqueConstraint("uuid", name="t_rpoblem_uuid_key"),
        UniqueConstraint("title", name="t_rpoblem_title_key"),
    )
    
    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    uuid = Column(
        UUID(as_uuid=True),
        nullable=False,
        default=uuid.uuid4   # 让 SQLAlchemy 自动生成 uuid
    )
    
    title = Column(Text, nullable=False)
    
    description = Column(Text, nullable=False)
    
    problem_type = Column(Integer, nullable = False)
    
    difficulty = Column(Integer, nullable = False)
    
    categories = Column(Text, nullable=False)
    
    answer = Column(Text, nullable=False)
    
    created_by = Column(Text, nullable=False)
    
    create_time = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now()
    )
    
    del_flag = Column(
        Boolean,
        server_default="false",
        nullable=True
    )
    