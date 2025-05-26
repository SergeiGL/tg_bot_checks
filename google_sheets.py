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
    return service.spreadsheets()


async def get_sheets_service():
    """
    Asynchronously get the Google Sheets API service by offloading
    the blocking build/credential step to a thread executor.
    """
    loop = asyncio.get_running_loop()
    sheets_api = await loop.run_in_executor(None, _sync_get_sheets_service)
    return sheets_api


async def find_row_number(target: str, spreadsheet_id: str) -> int | None:
    """
    Asynchronously looks up `target` in column A of the given spreadsheet.
    Returns the 1-based row number if found, or None otherwise.
    Also colors the A:idx cell to green
    """
    # Get the sheets service (runs in executor)
    sheets_api = await get_sheets_service()

    # Prepare the request object (non-blocking)
    request = sheets_api.values().get(spreadsheetId=spreadsheet_id, range="A:A")

    # Execute the request in a thread executor (blocking network I/O)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, request.execute)

    values = result.get("values", [])  # values is a list of [cell_value] lists

    for idx, row in enumerate(values, start=1):
        # Each row is a list; if the cell is empty, row may be an empty list
        cell_value = row[0].strip().replace("@", "") if len(row) > 0 else ""
        if cell_value == target:
            return idx

    return None

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
    values_request = sheets_api.values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{config.google_sheet_name}!B{row_number}:D{row_number}",
        valueInputOption="USER_ENTERED",
        body={
            "values": [
                [f"# {count+1}", f"{sum_to_pay} RUB", f"{str(elapsed_interval).split(".", 1)[0]}"]
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

    batch_update_request = sheets_api.batchUpdate(
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

    request = sheets_api.values().get(
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
        row_num = await find_row_number(TARGET_VAL, config.google_sheet_id)
        print(row_num)


    asyncio.run(main())