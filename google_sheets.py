import asyncio
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import config

def _sync_get_sheets_service():
    """
    Synchronous helper to create a Google Sheets API service object.
    """
    creds = Credentials.from_service_account_file("google_sheets_key.json", scopes=["https://www.googleapis.com/auth/spreadsheets"])
    service = build("sheets", "v4", credentials=creds)
    return service  # Return the main service


async def get_sheets_service():
    """
    Asynchronously get the Google Sheets API service by offloading
    the blocking build/credential step to a thread executor.
    """
    loop = asyncio.get_running_loop()
    sheets_api = await loop.run_in_executor(None, _sync_get_sheets_service)
    return sheets_api


async def get_row_and_color(target: str, spreadsheet_id: str) -> tuple[int | None, str | None]:
    """
    Asynchronously looks up `target` in column A of the given spreadsheet.
    Returns a tuple of (1-based row number, background color) if found, or None otherwise.
    Also colors the A:idx cell to green when found.
    """
    # Get the sheets service (runs in executor)
    sheets_api = await get_sheets_service()
    
    # First, get the values from column A
    values_request = sheets_api.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range="A:A")
    
    # Execute the values request in a thread executor (blocking network I/O)
    loop = asyncio.get_running_loop()
    values_result = await loop.run_in_executor(None, values_request.execute)
    values = values_result.get("values", [])  # values is a list of [cell_value] lists
    
    # Find the target row
    target_row = None
    for idx, row in enumerate(values, start=1):
        # Each row is a list; if the cell is empty, row may be an empty list
        cell_value = row[0].strip().replace("@", "") if len(row) > 0 else ""
        if cell_value == target:
            target_row = idx
            break
    
    if target_row is None:
        return (None, None)
    
    # Get the current formatting to read the background color
    cell_range = f"A{target_row}"
    format_request = sheets_api.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        ranges=[cell_range],
        includeGridData=True
    )
    
    format_result = await loop.run_in_executor(None, format_request.execute)
    
    grid_data = format_result.get("sheets", [{}])[0].get("data", [{}])[0]
    row_data = grid_data.get("rowData", [{}])
    cell_data = row_data[0].get("values", [{}])[0]
    
    current_bg_color = None
    if "effectiveFormat" in cell_data:
        current_bg_color = cell_data["effectiveFormat"].get("backgroundColor", None)

    return (target_row, current_bg_color)

async def color_row_and_insert_data(
    row_number: int,
    count: int,
    sum_to_pay: int,
    elapsed_interval: str,
    spreadsheet_id: str
):
    """
    Inserts `count` into column B, `sum_to_pay` into column C, and `elapsed_interval` into column D
    of the given `row_number` in the specified Google Sheets spreadsheet, and colors A:D of that row green.
    Returns nothing (performs the API calls).
    """
    # 1. Get the Sheets API client (this is IO-bound, hence we `await` it).
    sheets_api = await get_sheets_service()

    # 2. First, update the values in B:D of the target row.
    values_request = sheets_api.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{config.google_sheet_name}!B{row_number}:D{row_number}",
        valueInputOption="USER_ENTERED",
        body={
            "values": [
                [f"# {count+1}", sum_to_pay, f"{str(elapsed_interval).split(".", 1)[0]}"]
            ]
        }
    )

    # 3. Since the Sheets client is synchronous under the hood, run .execute() in a thread-pool.
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, values_request.execute)

    format_request_body = {
        "requests": [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": 0,
                        "startRowIndex": row_number - 1,
                        "endRowIndex": row_number,
                        "startColumnIndex": 0,
                        "endColumnIndex": 4
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
        spreadsheetId=spreadsheet_id,
        body=format_request_body
    )

    # 6. Execute the batchUpdate in the thread-pool as well.
    await loop.run_in_executor(None, batch_update_request.execute)



async def get_n_people_and_total_sum(spreadsheet_id: str):
    """
    Fetches the values in cells C2 (n_people) and D2 (total_sum) from the given Google Sheets spreadsheet.
    Returns a tuple of two integers: (n_people, total_sum).
    """
    # Get the sheets service (runs in executor)
    sheets_api = await get_sheets_service()

    request = sheets_api.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="F2:G2"
    )

    # Execute the request in a thread executor (blocking network I/O)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, request.execute)

    values = result.get("values", [])
    if not values or not values[0]:
        raise ValueError("No data found in cells F2:G2")

    row = values[0]
    try:
        n_people = int(row[0].replace(",", ""))
    except (IndexError, ValueError):
        raise ValueError(f"Invalid or missing integer in F2: {row[0] if row else None}")

    try:
        total_sum = int(row[1].replace(",", ""))
    except (IndexError, ValueError):
        raise ValueError(f"Invalid or missing integer in G2: {row[1] if len(row) > 1 else None}")

    return n_people, total_sum



if __name__ == "__main__":
    async def main():
        TARGET_VAL = "julibusygina"
        data = await get_row_and_color(TARGET_VAL, config.google_sheet_id)
        print(data)


    asyncio.run(main())