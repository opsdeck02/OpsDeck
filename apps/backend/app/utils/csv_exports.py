import csv
import io

from fastapi.responses import Response


def build_csv_response(
    *,
    filename: str,
    fieldnames: list[str],
    rows: list[dict[str, object | None]],
) -> Response:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: format_csv_value(row.get(key))
                for key in fieldnames
            }
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def format_csv_value(value: object | None) -> str:
    if value is None:
        return ""
    return str(value)
