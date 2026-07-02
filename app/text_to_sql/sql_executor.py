
import logging
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import ( OperationalError, ProgrammingError,  DataError, StatementError, )

logger = logging.getLogger(__name__)

# 실행 결과 최대 행 수 (validator의 LIMIT과 이중으로 방어)
HARD_MAX_ROWS = 200


class SQLExecutionError(Exception):
    """SQL 실행 중 발생한 오류. 원본 DB 오류 메시지를 포함합니다."""
    pass


def execute_sql(
    db: Session,
    sql: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    logger.info(f"[SQL 실행] 쿼리: {sql}")

    try:
        # params 딕셔너리로 파라미터 바인딩 
        #   나쁜 예: db.execute(text(f"... WHERE id = {member_id}")) => 이 경우 member_id 변수에 "1 OR 1=1"같은 문자열 삽입 가능
        #   좋은 예: db.execute(text("... WHERE id = :member_id"), {"member_id": member_id})
        result = db.execute(text(sql), params)

        columns = list(result.keys()) #컬럼명 목록
        rows = result.fetchmany(HARD_MAX_ROWS) #최대 HARD_MAX_ROWS 행만

        result_list = [
            {col: _serialize_value(val) for col, val in zip(columns, row)}
            for row in rows
        ]

        
        return result_list

    except ProgrammingError as e:
        error_msg = f"SQL 문법 또는 스키마 오류: {str(e.orig or e)}"
        logger.warning(f"[SQL 실행] ProgrammingError: {error_msg}")
        raise SQLExecutionError(error_msg) from e

    except DataError as e:
        error_msg = f"데이터 타입 오류: {str(e.orig or e)}"
        logger.warning(f"[SQL 실행] DataError: {error_msg}")
        raise SQLExecutionError(error_msg) from e

    except OperationalError as e:
        error_msg = f"데이터베이스 운영 오류: {str(e.orig or e)}"
        logger.error(f"[SQL 실행] OperationalError: {error_msg}")
        raise SQLExecutionError(error_msg) from e

    except StatementError as e:
        error_msg = f"파라미터 바인딩 오류: {str(e)}"
        logger.error(f"[SQL 실행] StatementError: {error_msg}")
        raise SQLExecutionError(error_msg) from e

    except Exception as e:
        error_msg = f"예상치 못한 오류: {str(e)}"
        logger.error(f"[SQL 실행] 알 수 없는 오류: {error_msg}")
        raise SQLExecutionError(error_msg) from e

# DB 결과값과 타입을 JSON 직렬화 가능한 형태로 변환
def _serialize_value(value: Any) -> Any:
    from datetime import datetime, date
    from decimal import Decimal
    if value is None:
        return None
    if isinstance(value, Decimal):
        # Decimal → float (JSON 직렬화를 위해)
        return float(value)
    if isinstance(value, (datetime, date)):
        # datetime → ISO 8601 문자열
        return value.isoformat()
    return value
