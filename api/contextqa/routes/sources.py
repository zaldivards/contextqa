from typing import Annotated

from fastapi import APIRouter, HTTPException, UploadFile, Depends, status, Query
from sqlalchemy.orm import Session

from contextqa import context, get_logger
from contextqa.models.schemas import SimilarityProcessor, SourceStatus, IngestionResult, Source, SourcesList
from contextqa.routes.dependencies import get_db
from contextqa.services.sources import sources_exists, get_sources
from contextqa.utils.exceptions import VectorDBConnectionError, DuplicatedSourceError

LOGGER = get_logger()


router = APIRouter()


@router.post("/ingest/", response_model=IngestionResult)
def ingest_source(documents: list[UploadFile], session: Annotated[Session, Depends(get_db)]):
    """Ingest sources used by the QA session"""
    try:
        context_manager = context.get_setter(SimilarityProcessor.LOCAL)
        processor = context.BatchProcessor(manager=context_manager)
        # pylint: disable=E1102
        return processor.persist(documents, session)
    except DuplicatedSourceError as ex:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "The source already exists and it doesn't have updated content",
                "cause": str(ex),
            },
        ) from ex
    except VectorDBConnectionError as ex:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail={
                "message": (
                    "Connection error trying to set the context using the selected vector store. Please double check"
                    " your credentials"
                ),
                "cause": str(ex),
            },
        ) from ex
    except Exception as ex:
        LOGGER.exception("Error while setting context. Cause: %s", ex)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "ContextQA server did not process the request successfully", "cause": str(ex)},
        ) from ex


@router.get("/check-availability/", response_model=SourceStatus)
async def check_sources(session: Annotated[Session, Depends(get_db)]):
    """Check the availability of at least one source"""
    try:
        status_flag = sources_exists(session)
        return SourceStatus.from_count_status(status_flag)
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "ContextQA could not get the results from the DB", "cause": str(ex)},
        ) from ex


@router.get("/", response_model=SourcesList)
async def get_active_sources(
    session: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1)] = 10,
    skip: Annotated[int, Query(ge=0)] = 0,
):
    """List active sources"""
    try:
        sources, total = get_sources(session, limit, skip)
        return SourcesList(
            sources=[Source(id=source.id, title=source.name, digest=source.digest) for source in sources], total=total
        )
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "ContextQA could not get the results from the DB", "cause": str(ex)},
        ) from ex
