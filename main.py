import flet as ft
def main(page: ft.Page):
    page.title = "Primera app"
    texto = ft.Text("Hola, Gabriel")
    page.add(texto)

ft.app(target=main)
