# generate_pico_token.py
from auth import generate_token
# identity pode ser 'pico' ou qualquer string
token = generate_token("pico-device", hours=24*365)  # 1 ano
print(token)
