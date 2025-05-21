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


async def find_and_green_cell(target: str, spreadsheet_id: str) -> int | None:
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
            # ====== Write code here to color the A:idx cell to green ======

            # 1. First, retrieve the sheet ID (we assume the target is on the first sheet,
            #    but you can adjust to locate a different sheet by name/index if needed).
            metadata_request = sheets_api.get(spreadsheetId=spreadsheet_id)
            metadata = await loop.run_in_executor(None, metadata_request.execute)
            # Assume the first sheet in the spreadsheet
            # [{'properties': {'sheetId': 0, 'title': 'payments', 'index': 0, 'sheetType': 'GRID', 'gridProperties': {'rowCount': 1002, 'columnCount': 24}}}]
            sheet_id = metadata["sheets"][0]["properties"]["sheetId"]

            # 2. Prepare a repeatCell request to set the backgroundColor of A:idx to green.
            #    Note: API uses zero-based indexes, so row index is idx-1, column 'A' is 0.
            requests = [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": idx - 1,
                            "endRowIndex": idx,
                            "startColumnIndex": 0,
                            "endColumnIndex": 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {
                                    "red": 0.0,
                                    "green": 1.0,
                                    "blue": 0.0,
                                }
                            }
                        },
                        "fields": "userEnteredFormat.backgroundColor",
                    }
                }
            ]

            # 3. Send the batchUpdate request to apply the formatting.
            body = {"requests": requests}
            batch_update_request = sheets_api.batchUpdate(
                spreadsheetId=spreadsheet_id,
                body=body
            )
            await loop.run_in_executor(None, batch_update_request.execute)

            # ====== Done coloring the cell green ======
            return idx

    return None


if __name__ == "__main__":
    async def main():
        TARGET_VAL = "julibusygina"
        row_num = await find_and_green_cell(TARGET_VAL, config.google_sheet_id)
        print(row_num)


    asyncio.run(main())