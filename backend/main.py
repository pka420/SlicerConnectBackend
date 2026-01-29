from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import Base, engine
from api.auth import router as auth_router
from api.projects import router as projects_router
from api.collaboration import router as collab_router
from api.segmentations import router as segmentations_router
from api.users import router as users_router

app = FastAPI(title="User Authentication API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

app.include_router(auth_router, tags=["Authentication"])
app.include_router(projects_router, tags=["Projects"])
app.include_router(collab_router, tags=["Collaboration"])
app.include_router(segmentations_router, tags=["Segmentations"])
app.include_router(users_router, tags=["Users"])

@app.get("/")
def root():
    return {"message": "Backend is running!"}
