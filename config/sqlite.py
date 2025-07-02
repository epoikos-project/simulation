from fastapi.params import Depends
from sqlalchemy.sql.annotation import Annotated
from sqlmodel import Session, create_engine


sqlite_file_name = "data/database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread": False, "thread_safety": "multi_threaded"}
engine = create_engine(sqlite_url, connect_args=connect_args)


def get_session():
    with Session(engine) as session:
        yield session


DB = Annotated[Session, Depends(get_session)]
