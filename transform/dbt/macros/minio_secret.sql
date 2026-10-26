{% macro configure_minio_s3_secret() %}
  {% if target.name == 'minio' %}
    {% set endpoint = env_var('AWS_ENDPOINT_URL', 'http://minio:9000') | replace('http://', '') | replace('https://', '') %}
    {% set access_key = env_var('AWS_ACCESS_KEY_ID', '') | replace("'", "''") %}
    {% set secret_key = env_var('AWS_SECRET_ACCESS_KEY', '') | replace("'", "''") %}
    {% set region = env_var('AWS_REGION', 'us-east-1') | replace("'", "''") %}
    {% set use_ssl = 'true' if env_var('AWS_ENDPOINT_URL', '').startswith('https') else 'false' %}
    CREATE OR REPLACE SECRET vnecom_minio_s3 (
      TYPE S3,
      KEY_ID '{{ access_key }}',
      SECRET '{{ secret_key }}',
      REGION '{{ region }}',
      ENDPOINT '{{ endpoint }}',
      URL_STYLE 'path',
      USE_SSL {{ use_ssl }}
    );
  {% endif %}
{% endmacro %}
