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

    async with get_connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute('''SELECT * FROM visitors WHERE name = %s AND module = %s''', (client_ip, "DEX-DASH"))
            result = await cursor.fetchone()

            if result:
                times = result[3] + 1
                await cursor.execute('''UPDATE visitors SET times = %s WHERE name = %s AND module = %s''', (times, client_ip, "DEX-DASH"))
                await cursor.execute('''UPDATE visitors SET last_time = NOW() WHERE name = %s AND module = %s''', (client_ip, "DEX-DASH"))
                await conn.commit()
            else:
                await cursor.execute('''INSERT INTO visitors (name, module, times, first_time, last_time) VALUES (%s, %s, %s, NOW(), NOW())''', (client_ip, "DEX-DASH", 1))
                await conn.commit()

    return {"message": "Success"}

@router.get("/used-rd-medics")
async def usedRdMedics(request: Request):
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

    async with get_connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute('''SELECT * FROM visitors WHERE name = %s AND module = %s''', (client_ip, "RD-MEDICS"))
            result = await cursor.fetchone()

            if result:
                times = result[3] + 1
                await cursor.execute('''UPDATE visitors SET times = %s WHERE name = %s AND module = %s''', (times, client_ip, "RD-MEDICS"))
                await cursor.execute('''UPDATE visitors SET last_time = NOW() WHERE name = %s AND module = %s''', (client_ip, "RD-MEDICS"))
                await conn.commit()
            else:
                await cursor.execute('''INSERT INTO visitors (name, module, times, first_time, last_time) VALUES (%s, %s, %s, NOW(), NOW())''', (client_ip, "RD-MEDICS", 1))
                await conn.commit()

    return {"message": "Success"}