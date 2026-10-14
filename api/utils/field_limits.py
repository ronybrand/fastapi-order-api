from decimal import Decimal

# Limites de entrada alinhados ao que o banco aceita de fato: um valor acima disso nao deve chegar ao
# INSERT (onde viraria um erro de coluna, ou seja, 500) e sim ser recusado como 400 no schema.
MAX_NAME_LENGTH = 200
MAX_EMAIL_LENGTH = 320
# items.unit_price e Numeric(10, 2): 8 digitos inteiros + 2 decimais.
MAX_UNIT_PRICE = Decimal("99999999.99")
# Por linha de item: mantem o total de um pedido longe de valores absurdos.
MAX_QUANTITY = 10_000
# O documento so conta como tal se tiver conteudo alem da pontuacao.
MIN_TAX_ID_SIGNIFICANT_CHARS = 5
