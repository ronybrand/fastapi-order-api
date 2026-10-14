from collections import OrderedDict


class RecentMessageIds:
    """Memoria limitada dos ids de mensagem ja entregues por e-mail. O RabbitMQ e at-least-once: uma
    mensagem cujo ack se perdeu volta e mandaria um segundo e-mail. Isso so cobre reentregas vistas
    pelo mesmo processo do worker - mitigacao barata, nao exactly-once distribuido."""

    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._ids: OrderedDict[str, None] = OrderedDict()

    def add(self, message_id: str) -> None:
        self._ids[message_id] = None
        self._ids.move_to_end(message_id)
        while len(self._ids) > self._capacity:
            self._ids.popitem(last=False)

    def __contains__(self, message_id: object) -> bool:
        return message_id in self._ids
