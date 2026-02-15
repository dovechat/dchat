Data flow:
Входящее сообщение (Telegram → Фронт):

Фронт открывает диалог → WebSocket подключается к chat:8001/ws/chat/{conversationId}
websocket_manager принимает соединение → вызывает listener.start_listening
Листенер берёт session_string из channel_accounts по my_phone
Создаёт Telethon клиент, подключается к Telegram
Когда приходит сообщение от peer_phone → сохраняет в БД → пушит на фронт через WebSocket

Исходящее сообщение (Фронт → Telegram):

Фронт POST /api/v1/messages на chat:8001
chat_service.create_message → сохраняет в БД
Вызывает listener.send_message → берёт уже существующий Telethon клиент
Отправляет сообщение в Telegram