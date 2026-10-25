import dagster as dg

# logical capture date in ICT; end_offset=1 so "today" is a valid partition for intraday captures
daily_ict = dg.DailyPartitionsDefinition(start_date="2025-01-01", timezone="Asia/Ho_Chi_Minh", end_offset=1)
