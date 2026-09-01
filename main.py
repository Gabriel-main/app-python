from pydoc import text

import flet as ft

def main(page: ft.Page):

    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.title = "Primera app"
    texto = ft.Text("Hola, Gabriel")
    texto2 = ft.Text("Vamos a ver que tal")
    page.add(texto, texto2)

    def cambiar_texto(e):
        texto.value = "Vas bien " + texto.value[5:]
        page.update()

    boton = ft.ElevatedButton("Cambiar texto", on_click=cambiar_texto)
    page.add(boton)

ft.app(target=main)
