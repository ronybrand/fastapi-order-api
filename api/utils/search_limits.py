# Tetos estruturais do payload de busca: sem eles um unico request carrega centenas de
# condicoes/valores para o banco (ver SearchRequest e api/utils/pagination.py).
MAX_FILTER_FIELDS = 10
MAX_CONDITIONS_PER_FIELD = 10
MAX_IN_VALUES = 100
MAX_VALUE_LENGTH = 200
# OFFSET precisa caber num inteiro de 32 bits: acima disso o Postgres devolve erro em vez de
# uma pagina vazia (page * size e calculado em Python, sem limite proprio).
MAX_OFFSET = 2_147_483_647
