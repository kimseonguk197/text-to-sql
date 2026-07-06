import logging
from sqlalchemy.orm import Session

from app.text_to_sql.sql_generator import generate_sql, fix_sql
from app.text_to_sql.sql_validator import validate_and_correct
from app.text_to_sql.sql_executor import execute_sql
from app.text_to_sql.llm_response import format_sql_result, format_error_response

logger = logging.getLogger(__name__)


def call_sql_pipeline(
    user_message: str,
    db: Session,
    current_member_id: int,
) -> str:
    current_sql = ""
    last_error = ""
    retry_count = 0
    #  Self-Healing : 실패시 최대 반복 재시도 3회
    for attempt in range(3):
        # 1.SQL 생성 또는 수정 
        if attempt == 0:
            logger.info(f"[Text-to-SQL] SQL 생성 시도 #{attempt + 1}")
            current_sql = generate_sql(user_message)
        else:
            # 이전 오류를 기반으로 SQL 수정 (Self-Correction)
            logger.info(
                f"[Text-to-SQL] SQL 수정 시도 #{attempt + 1} | "
                f"이전 오류: {last_error[:60]}..."
            )
            current_sql = fix_sql(current_sql, last_error)
            retry_count = attempt

        # 2.SQL 검증 
        validation = validate_and_correct(current_sql)

        if not validation.is_valid:
            # 검증 위반 중에서 타인 데이터 접근 시도는 Self-Correction 없이 즉시 차단
            if validation.is_unauthorized:
                logger.warning("[Text-to-SQL] 타인 데이터 접근 시도 감지 → 즉시 차단")
                return "다른 사용자의 데이터는 조회할 수 없습니다."
            last_error = str(validation)
            continue

        # 3.SQL 실행
        try:
            execution_params = {"current_member_id": current_member_id,}
            corrected_sql = validation.corrected_sql
            results = execute_sql(db, corrected_sql, execution_params)

            logger.info(
                f"[Text-to-SQL] 성공 | {len(results)}건 조회 | 재시도={retry_count}회"
            )
            response_text = format_sql_result(user_message, results)
            return response_text

        except Exception as e:
            # SQL 실행 실패 → 오류 메시지를 다음 재시도에 전달
            last_error = str(e)
            logger.warning(
                f"[Text-to-SQL] 실행 실패 (시도 #{attempt + 1}): {last_error}"
            )
            continue

    # 모든 재시도 실패시
    return format_error_response(user_message, last_error)
