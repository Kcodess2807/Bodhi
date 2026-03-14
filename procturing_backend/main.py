from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from loguru import logger
import uvicorn
from .config import settings
from .WebSockets.proctoring_ws import proctoring_router
from .router.enrollment import enrollment_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up Proctoring API")

    logger.info("pre-loading the cv models")
    from .services.proctoring.face_detection import FaceDetector
    from .services.proctoring.identity_detection import IdentityVerifier
    from .services.proctoring.gaze_analysis import GazeAnalyzer
    from .services.proctoring.object_detection import ObjectDetector

    app.state.face_detector=FaceDetector()
    app.state.identity_verifier=IdentityVerifier()
    app.state.gaze_analyzer=GazeAnalyzer()
    app.state.object_detector=ObjectDetector()
    logger.info("models ready and loaded to be used!!")

    yield




app=FastAPI(
    title="Proctoring API",
    description="AI-powered proctoring platform backend",
    version="1.0.0",
    lifespan=lifespan,
)

#CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#ROUTERS
app.include_router(proctoring_router)
app.include_router(enrollment_router)


#HEALTH CHECKUP
@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "ok",
        "models_loaded": {
            "face_detector": hasattr(app.state, "face_detector"),
            "identity_verifier": hasattr(app.state, "identity_verifier"),
            "gaze_analyzer": hasattr(app.state, "gaze_analyzer"),
            "object_detector": hasattr(app.state, "object_detector"),
        },
    }


if __name__=="__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info",
    )