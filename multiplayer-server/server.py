import asyncio
import websockets
import json
import math

# Константы наград по местам
REWARDS = {1: 25, 2: 18, 3: 15, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4}


class GameRoom:
    def __init__(self, room_id):
        self.room_id = room_id
        self.players = {}  # {websocket: {"username": str, "car_level": int, "pos": dict}}
        self.state = "waiting"  # waiting, playing, finished
        self.finishers = []

    async def broadcast(self, message):
        if self.players:
            await asyncio.wait([ws.send(json.dumps(message)) for ws in self.players.keys()])


rooms = {}


async def handler(websocket, path):
    try:
        async for message in websocket:
            data = json.loads(message)
            action = data.get("action")

            if action == "join":
                # Логика матчмейкинга: ищем свободную комнату
                room = next((r for r in rooms.values() if r.state == "waiting" and len(r.players) < 5), None)
                if not room:
                    room_id = f"room_{len(rooms) + 1}"
                    room = GameRoom(room_id)
                    rooms[room_id] = room

                room.players[websocket] = {
                    "username": data["username"],
                    "car_level": data["car_level"],
                    "x": 0, "y": 0, "angle": 180,
                    "lap": 0, "finished": False
                }
                await websocket.send(json.dumps({"action": "joined", "room": room.room_id}))

                # Если 5 человек или принудительный старт - начинаем
                if len(room.players) >= 5:  # В реале тут таймер на 10 сек
                    room.state = "playing"
                    # Добиваем ботами до 8 машин на клиенте
                    await room.broadcast({"action": "start_game", "real_players": len(room.players)})

            elif action == "update_pos":
                room_id = data["room"]
                room = rooms.get(room_id)
                if room:
                    room.players[websocket].update({
                        "x": data["x"], "y": data["y"], "angle": data["angle"]
                    })
                    # Отправляем всем координаты друг друга
                    state_data = {
                        "action": "sync",
                        "players": [{"user": p["username"], "x": p["x"], "y": p["y"], "angle": p["angle"]} for p in
                                    room.players.values()]
                    }
                    await room.broadcast(state_data)

            elif action == "finish":
                room_id = data["room"]
                room = rooms.get(room_id)
                if room and websocket not in room.finishers:
                    room.finishers.append(websocket)
                    place = len(room.finishers)
                    car_level = room.players[websocket]["car_level"]

                    # ФОРМУЛА НАГРАДЫ:
                    coef = 1.0 + (car_level - 1) * 0.03
                    reward = math.floor(REWARDS.get(place, 0) * coef)

                    # Отправляем игроку его результат
                    await websocket.send(json.dumps({
                        "action": "race_result",
                        "place": place,
                        "coins_earned": reward,
                        "prize_car": 1  # Всегда даем нищую машину 1 уровня
                    }))

                    # В реале здесь сервер делает POST запрос к БД PostgreSQL,
                    # чтобы начислить reward и машинку на баланс юзера.

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        # Очистка при отключении
        for room in rooms.values():
            if websocket in room.players:
                del room.players[websocket]


start_server = websockets.serve(handler, "0.0.0.0", 8080)

if __name__ == "__main__":
    print("Multiplayer Server Started on port 8080...")
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()