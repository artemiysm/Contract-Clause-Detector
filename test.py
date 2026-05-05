import os

print("📁 Текущая директория:", os.getcwd())
print("📁 templates существует:", os.path.exists('templates'))
print("📁 templates/index.html существует:", os.path.exists('templates/index.html'))
print("📁 static существует:", os.path.exists('static'))

# Проверка относительных путей
print("\n🔍 Относительные пути:")
print("  ../templates:", os.path.exists('../templates'))
print("  ../../templates:", os.path.exists('../../templates'))