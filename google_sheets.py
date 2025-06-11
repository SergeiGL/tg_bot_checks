import asyncio
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import config
from concurrent.futures import ThreadPoolExecutor
import functools

# Reduced thread pool size for better resource management
_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="sheets-api")

# Cache the service instance - no need for LRU cache with maxsize=32 for a single service
_sheets_service = None

def _create_sheets_service():
    """Create Google Sheets API service object once."""
    global _sheets_service
    if _sheets_service is None:
        creds = Credentials.from_service_account_file(
            "google_sheets_key.json", 
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        _sheets_service = build("sheets", "v4", credentials=creds)
    return _sheets_service

async def get_sheets_service():
    """Get the cached Google Sheets API service."""
    if _sheets_service is None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_executor, _create_sheets_service)
    return _sheets_service

async def _execute_request(request):
    """Execute a Google Sheets API request in thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, request.execute)

async def fetch_list() -> dict | None:
    """Fetch data from specified ranges in a single batch request."""
    try:
        sheets_api = await get_sheets_service()
        
        # Single batch request for all needed data
        batch_request = sheets_api.spreadsheets().values().batchGet(
            spreadsheetId=config.google_sheet_id,
            ranges=[
                f"{config.google_sheet_name}!A2:A",
                f"{config.google_sheet_name}!F2",
                f"{config.google_sheet_name}!G2"
            ]
        )
        
        response = await _execute_request(batch_request)
        value_ranges = response.get('valueRanges', [])
        
        # Process column A data
        column_A_data = []
        if value_ranges and 'values' in value_ranges[0]:
            column_A_data = [
                str(row[0]).replace("@", "").strip() 
                for row in value_ranges[0]['values'] 
                if row and row[0]
            ]
        
        # Process F2 value (total_people)
        total_people = None
        if len(value_ranges) > 1 and 'values' in value_ranges[1] and value_ranges[1]['values']:
            try:
                total_people = int(value_ranges[1]['values'][0][0].replace(",", "").replace(".", ""))
            except (ValueError, IndexError):
                pass
        
        # Process G2 value (total_sum)
        total_sum = None
        if len(value_ranges) > 2 and 'values' in value_ranges[2] and value_ranges[2]['values']:
            try:
                total_sum = int(value_ranges[2]['values'][0][0].replace(",", "").replace(".", ""))
            except (ValueError, IndexError):
                pass
        
        return {
            'column_A_list': column_A_data,
            'total_people': total_people,
            'total_sum': total_sum
        }
        
    except Exception:
        return None

async def color_and_insert_data(
    username: str,
    count: int,
    sum_to_pay: int,
    elapsed_interval: str,
) -> int:
    """
    Insert data and format row in a single batch operation.
    Returns the row number if successful, None otherwise.
    """
    try:
        sheets_api = await get_sheets_service()

        # Get column A values to find the target row
        values_request = sheets_api.spreadsheets().values().get(
            spreadsheetId=config.google_sheet_id, 
            range=f"{config.google_sheet_name}!A:A"
        )
        
        response = await _execute_request(values_request)
        values = response.get("values", [])
        
        # Find target row number
        row_number = None
        for idx, row in enumerate(values, start=1):
            if row:  # Check if row is not empty
                cell_value = str(row[0]).strip().replace("@", "") if row[0] else ""
                if cell_value == username:
                    row_number = idx
                    break
        
        if row_number is None:
            return None

        # Single batch request for both data update and formatting
        batch_request_body = {
            "requests": [
                # Update values
                {
                    "updateCells": {
                        "range": {
                            "sheetId": 0,
                            "startRowIndex": row_number - 1,
                            "endRowIndex": row_number,
                            "startColumnIndex": 1,  # Column B
                            "endColumnIndex": 4     # Up to column D
                        },
                        "rows": [
                            {
                                "values": [
                                    {"userEnteredValue": {"stringValue": f"# {count+1}"}},
                                    {"userEnteredValue": {"numberValue": sum_to_pay}},
                                    {"userEnteredValue": {"stringValue": str(elapsed_interval).split(".", 1)[0]}}
                                ]
                            }
                        ],
                        "fields": "userEnteredValue"
                    }
                },
                # Apply green background formatting
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": 0,
                            "startRowIndex": row_number - 1,
                            "endRowIndex": row_number,
                            "startColumnIndex": 0,  # Column A
                            "endColumnIndex": 4     # Up to column D
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {
                                    "red": 0.0,
                                    "green": 1.0,
                                    "blue": 0.0
                                }
                            }
                        },
                        "fields": "userEnteredFormat.backgroundColor"
                    }
                }
            ]
        }

        batch_update_request = sheets_api.spreadsheets().batchUpdate(
            spreadsheetId=config.google_sheet_id,
            body=batch_request_body
        )

        await _execute_request(batch_update_request)
        return row_number
        
    except Exception:
        return None