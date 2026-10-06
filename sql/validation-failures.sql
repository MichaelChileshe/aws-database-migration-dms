-- What a validation-only task found, by table and failure type, plus three examples.
SELECT TABLE_NAME, FAILURE_TYPE, COUNT(*) AS failures
  FROM awsdms_control.awsdms_validation_failures_v1
 GROUP BY TABLE_NAME, FAILURE_TYPE ORDER BY TABLE_NAME, FAILURE_TYPE;
SELECT TABLE_NAME, FAILURE_TYPE, `KEY`, LEFT(DETAILS, 120) AS details
  FROM awsdms_control.awsdms_validation_failures_v1
 ORDER BY FAILURE_TIME DESC LIMIT 3;
