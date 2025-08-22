from fastapi import APIRouter, Request
from db import get_connection

router = APIRouter()

@router.get("/used-dex-dash")
async def usedDexDash(request: Request):
    client_ip = (
    request.headers.get("x-real-ip")
    or request.headers.get("X-Forwarded-For")
    or request.client.host
)

    try:
        print(dict(request.headers))
        print(client_ip)
        print(request.headers.get("x-real-ip"))
    except Exception as e:
        print("Exception occurred while getting request.headers: " + e)

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''SELECT * FROM visitors WHERE name = %s''', (client_ip,))
            result = cursor.fetchone()

            if result:
                times = result[3] + 1
                cursor.execute('''UPDATE visitors SET times = %s WHERE name = %s''', (times, client_ip))
                cursor.execute('''UPDATE visitors SET last_time = NOW() WHERE name = %s''', (client_ip,))
                conn.commit()
            else:
                cursor.execute('''INSERT INTO visitors (name, module, times, first_time, last_time) VALUES (%s, %s, %s, NOW(), NOW())''', (client_ip, "DEX-DASH", 1))
                conn.commit()

    return {"message": "Success"}