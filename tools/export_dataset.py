from backend.db import Session
from backend.exports import export_dataset

with Session.begin() as session:
    print(export_dataset(session))
