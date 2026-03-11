import discord
from discord.ext import commands
import random
from PIL import Image
from io import BytesIO
from typing import Literal, Optional
import aiohttp
import html
import asyncio
from utils.constants import WANTED_TEMPLATE_URL
# Importamos nuestros helpers de API e integración de BD
from utils.api_helpers import ask_gemini, search_anime
from utils import database_manager as db

class TriviaView(discord.ui.View):
    def __init__(self, ctx: commands.Context, cog, correct_ans: str, prize: int):
        super().__init__(timeout=20.0)
        self.ctx = ctx
        self.cog = cog
        self.correct_ans = correct_ans
        self.prize = prize
        self.answered = False

    async def on_timeout(self):
        if not self.answered:
            for item in self.children: item.disabled = True
            embed = discord.Embed(title="⏰ ¡Tiempo agotado!", description=f"Nadie respondió a tiempo. La respuesta correcta era: **{self.correct_ans}**", color=discord.Color.red())
            try: await self.message.edit(embed=embed, view=self)
            except: pass

    async def check_answer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.answered: return
        
        if button.label == self.correct_ans or (len(self.correct_ans) > 77 and self.correct_ans.startswith(button.label.replace('...', ''))):
            self.answered = True
            for item in self.children:
                item.disabled = True
                if item.label == button.label: item.style = discord.ButtonStyle.success
            
            await db.update_balance(interaction.guild.id, interaction.user.id, wallet_change=self.prize)
            embed = discord.Embed(title="🎉 ¡Correcto!", description=f"{interaction.user.mention} conocía la respuesta: **{self.correct_ans}**.\nSe le han transferido directamente **+{self.prize}** monedas a su cartera.", color=discord.Color.green())
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message(f"❌ '{button.label}' es incorrecto.", ephemeral=True)

    @discord.ui.button(label="A", style=discord.ButtonStyle.primary)
    async def btn_a(self, interaction: discord.Interaction, button: discord.ui.Button): await self.check_answer(interaction, button)
    @discord.ui.button(label="B", style=discord.ButtonStyle.primary)
    async def btn_b(self, interaction: discord.Interaction, button: discord.ui.Button): await self.check_answer(interaction, button)
    @discord.ui.button(label="C", style=discord.ButtonStyle.primary)
    async def btn_c(self, interaction: discord.Interaction, button: discord.ui.Button): await self.check_answer(interaction, button)
    @discord.ui.button(label="D", style=discord.ButtonStyle.primary)
    async def btn_d(self, interaction: discord.Interaction, button: discord.ui.Button): await self.check_answer(interaction, button)

class ConfessionModal(discord.ui.Modal, title="Confesión Anónima"):
    texto = discord.ui.TextInput(label="Escribe tu secreto aquí", style=discord.TextStyle.paragraph, max_length=1500, placeholder="Nadie sabrá que fuiste tú, ni siquiera los administradores...", required=True)
    
    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🕵️ Confesión Anónima", description=self.texto.value, color=discord.Color.dark_purple())
        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("Confesión publicada exitosamente. Tu identidad está a salvo.", ephemeral=True)

class ConfessView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Confesarse", style=discord.ButtonStyle.secondary, emoji="🕵️", custom_id="confess_open_btn")
    async def open_confess(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ConfessionModal())




# --- DICCIONARIOS DE TRADUCCIÓN ---
# Para traducir campos que vienen en inglés de la API
STATUS_TRANSLATIONS = {
    "Finished Airing": "Finalizado",
    "Currently Airing": "En Emisión",
    "Not yet aired": "Próximamente"
}

GENRE_TRANSLATIONS = {
    "Action": "Acción", "Adventure": "Aventura", "Comedy": "Comedia", "Drama": "Drama",
    "Sci-Fi": "Ciencia Ficción", "Fantasy": "Fantasía", "Horror": "Terror", "Romance": "Romance",
    "Mystery": "Misterio", "Slice of Life": "Recuentos de la vida", "Supernatural": "Sobrenatural",
    "Sports": "Deportes", "Suspense": "Suspense", "Award Winning": "Galardonado"
}


class FunCog(commands.Cog, name="Juegos e IA"):
    """Comandos de juegos, IA y otros entretenimientos."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name='pregunta', description="Hazme cualquier pregunta y usaré mi IA para responder.")
    async def pregunta(self, ctx: commands.Context, *, pregunta: str):
        await ctx.defer()
        
        # Llamamos a nuestra función de ayuda centralizada
        respuesta_ia = await ask_gemini(self.bot.http_session, self.bot.GEMINI_API_KEY, pregunta)

        embed = discord.Embed(title="🤔 Pregunta para Umapyoi", description=f"**Tú preguntaste:**\n{pregunta}", color=discord.Color.gold())
        embed.add_field(name="💡 Mi Respuesta:", value=respuesta_ia)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='anime', description="Busca información detallada sobre un anime.")
    async def anime(self, ctx: commands.Context, *, nombre: str):
        await ctx.defer()
        
        anime_data = await search_anime(self.bot.http_session, nombre)

        if not anime_data:
            return await ctx.send(f"❌ No encontré ningún anime llamado `{nombre}`.", ephemeral=True)
        
        if "error" in anime_data:
            return await ctx.send(f"❌ Hubo un error con la API (Código: {anime_data['error']}). Inténtalo de nuevo más tarde.", ephemeral=True)

        # --- LÓGICA DE TRADUCCIÓN (SIN IA) ---

        # 1. Buscar el título en español
        title_es = next((t['title'] for t in anime_data.get('titles', []) if t['type'] == 'Spanish'), None)
        display_title = title_es or anime_data.get('title', 'N/A')

        # 2. Usar la sinopsis original en inglés para mayor fiabilidad
        synopsis = anime_data.get('synopsis', 'No hay sinopsis disponible.')
        if len(synopsis) > 1024:
            synopsis = synopsis[:1021] + "..."
        
        # 3. Traducir estado y géneros
        status_en = anime_data.get('status', 'N/A')
        status_es = STATUS_TRANSLATIONS.get(status_en, status_en)

        genres_en = [genre['name'] for genre in anime_data.get('genres', [])]
        genres_es = [GENRE_TRANSLATIONS.get(g, g) for g in genres_en]

        # --- CREACIÓN DEL EMBED ---
        embed = discord.Embed(
            title=display_title,
            url=anime_data.get('url', ''),
            description=synopsis,
            color=discord.Color.blue()
        )

        if image_url := anime_data.get('images', {}).get('jpg', {}).get('large_image_url'):
            embed.set_thumbnail(url=image_url)

        embed.add_field(name="Puntuación", value=f"⭐ {anime_data.get('score', 'N/A')}", inline=True)
        embed.add_field(name="Episodios", value=anime_data.get('episodes', 'N/A'), inline=True)
        embed.add_field(name="Estado", value=status_es, inline=True)

        if genres_es:
            embed.add_field(name="Géneros", value=", ".join(genres_es), inline=False)

        embed.set_footer(text=f"Fuente: MyAnimeList | ID: {anime_data.get('mal_id')}")

        await ctx.send(embed=embed)

    # --- Comandos que no usan APIs externas (se mantienen igual) ---

    def process_wanted_image(self, template_bytes: bytes, avatar_bytes: bytes) -> BytesIO:
        template = Image.open(BytesIO(template_bytes)).convert("RGBA")
        avatar = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
        avatar_size = (833, 820); paste_position = (96, 445)
        avatar = avatar.resize(avatar_size)
        template.paste(avatar, paste_position, avatar)
        final_buffer = BytesIO()
        template.save(final_buffer, format="PNG")
        final_buffer.seek(0)
        return final_buffer

    @commands.hybrid_command(name='wanted', description="Crea un cartel de 'Se Busca' para un usuario.")
    async def wanted(self, ctx: commands.Context, miembro: Optional[discord.Member] = None):
        await ctx.defer()
        miembro = miembro or ctx.author
        try:
            wanted_template_url = WANTED_TEMPLATE_URL 
            headers = {'User-Agent': 'Mozilla/5.0'}
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(wanted_template_url) as resp:
                    if resp.status != 200: return await ctx.send(f"❌ No pude descargar la plantilla. Estado: {resp.status}")
                    template_bytes = await resp.read()
                async with session.get(miembro.display_avatar.url) as resp:
                    if resp.status != 200: return await ctx.send("❌ No pude descargar el avatar.")
                    avatar_bytes = await resp.read()
            
            buffer = await self.bot.loop.run_in_executor(None, self.process_wanted_image, template_bytes, avatar_bytes)
            
            file = discord.File(buffer, filename="wanted.png")
            await ctx.send(file=file)
        except Exception as e:
            print(f"Error en /wanted: {e}")
            await ctx.send(f"❌ No pude crear el cartel. Error: {e}")

    @commands.hybrid_command(name='ppt', description="Juega Piedra, Papel o Tijera contra mí.")
    async def ppt(self, ctx: commands.Context, eleccion: Literal['piedra', 'papel', 'tijera']):
        opciones = ['piedra', 'papel', 'tijera']
        eleccion_usuario = eleccion.lower()
        eleccion_bot = random.choice(opciones)
        if eleccion_usuario == eleccion_bot:
            resultado = f"¡Empate! Ambos elegimos **{eleccion_bot}**."
        elif (eleccion_usuario == 'piedra' and eleccion_bot == 'tijera') or \
             (eleccion_usuario == 'papel' and eleccion_bot == 'piedra') or \
             (eleccion_usuario == 'tijera' and eleccion_bot == 'papel'):
            resultado = f"¡Ganaste! Yo elegí **{eleccion_bot}**."
        else:
            resultado = f"¡Perdiste! Yo elegí **{eleccion_bot}**."
        await ctx.send(f"Tú elegiste **{eleccion_usuario}**. {resultado}")

    # --- NUEVOS COMANDOS DE DIVERSIÓN ---

    @commands.hybrid_command(name="8ball", description="Pregúntale a la bola 8 mágica sobre tu futuro.")
    async def eight_ball(self, ctx: commands.Context, *, pregunta: str):
        respuestas = [
            "En mi opinión, sí.", "Es cierto.", "Es decididamente así.", "Probablemente.",
            "Buen pronóstico.", "Todo apunta a que sí.", "Sin duda.", "Sí.", "Puedes contar con ello.",
            "Respuesta vaga, vuelve a intentarlo.", "Pregunta en otro momento.", "Será mejor que no te lo diga ahora.",
            "No puedo predecirlo ahora.", "Concéntrate y vuelve a preguntar.", "No cuentes con ello.",
            "Mi respuesta es no.", "Mis fuentes me dicen que no.", "Las perspectivas no son buenas.", "Muy dudoso."
        ]
        respuesta = random.choice(respuestas)
        embed = discord.Embed(title="🎱 La Bola 8 Mágica", color=discord.Color.dark_blue())
        embed.add_field(name="Tu Pregunta", value=pregunta, inline=False)
        embed.add_field(name="Mi Respuesta", value=respuesta, inline=False)
        await ctx.send(embed=embed)



    @commands.hybrid_command(name="rolldice", description="Lanza uno o más dados.")
    async def rolldice(self, ctx: commands.Context, cantidad: int = 1, caras: int = 6):
        if cantidad > 100:
            return await ctx.send("No puedo lanzar más de 100 dados a la vez.", ephemeral=True)
        if caras > 1000:
            return await ctx.send("El dado no puede tener más de 1000 caras.", ephemeral=True)
        
        rolls = [random.randint(1, caras) for _ in range(cantidad)]
        total = sum(rolls)
        
        embed = discord.Embed(title="🎲 Lanzamiento de Dados", color=discord.Color.red())
        embed.add_field(name="Resultados", value=f"`{', '.join(map(str, rolls))}`", inline=False)
        if cantidad > 1:
            embed.add_field(name="Total", value=f"**{total}**", inline=False)
            
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="ship", description="Mide la compatibilidad entre dos personas.")
    async def ship(self, ctx: commands.Context, persona1: discord.Member, persona2: Optional[discord.Member] = None):
        target2 = persona2 or ctx.author
        
        # Para que el resultado sea siempre el mismo para la misma pareja
        seed = hash(f"{min(persona1.id, target2.id)}-{max(persona1.id, target2.id)}")
        random.seed(seed)
        
        percentage = random.randint(0, 100)
        
        if percentage < 20:
            comment = "Hmm... quizás solo como amigos."
        elif percentage < 40:
            comment = "Hay una pequeña chispa, ¿quizás?"
        elif percentage < 60:
            comment = "¡Una compatibilidad decente!"
        elif percentage < 80:
            comment = "¡Wow, aquí hay potencial!"
        else:
            comment = "¡Están hechos el uno para el otro! ❤️"
            
        # Barra de progreso
        filled_blocks = int(percentage / 10)
        empty_blocks = 10 - filled_blocks
        progress_bar = '🟥' * filled_blocks + '⬜' * empty_blocks

        embed = discord.Embed(
            title=f"💖 Test de Compatibilidad 💖",
            description=f"Analizando la conexión entre **{persona1.display_name}** y **{target2.display_name}**...",
            color=discord.Color.light_grey()
        )
        embed.add_field(name="Resultado", value=f"## `{percentage}%`\n`{progress_bar}`\n\n**{comment}**")
        
        await ctx.send(embed=embed)

    @commands.hybrid_group(name="gacha", description="Juega al gacha de personajes de anime.")
    async def gacha(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("🎰 **Comandos Disp:** `/gacha pull`, `/gacha list`", ephemeral=True)

    @gacha.command(name="pull", description="Tira del gacha por 500 monedas y obtén un personaje aleatorio.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def gacha_pull(self, ctx: commands.Context):
        await ctx.defer()
        apuesta = 500
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        emoji_currency = settings.get('currency_emoji', '🪙')
        
        wallet, _ = await db.get_balance(ctx.guild.id, ctx.author.id)
        if wallet < apuesta: return await ctx.send(f"❌ Efectivo insuficiente. Cada tirada cuesta **{apuesta:,} {emoji_currency}**.", ephemeral=True)
        
        await db.update_balance(ctx.guild.id, ctx.author.id, wallet_change=-apuesta)
        
        try:
            async with self.bot.http_session.get("https://api.jikan.moe/v4/random/characters") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    char_data = data['data']
                    char_name = char_data.get('name', 'Desconocido')
                    img_url = char_data.get('images', {}).get('jpg', {}).get('image_url')
                else:
                    char_name = random.choice(["Goku", "Naruto", "Luffy", "Saitama", "Rem", "Nezuko", "Levi"])
                    img_url = None
        except:
             char_name = "Komi-san (Error de conexión)"
             img_url = None
             
        # Generar Rareza
        r = random.randint(1, 1000)
        if r <= 10: rarity, stars, color = "Mítico", "⭐⭐⭐⭐⭐", discord.Color.gold()
        elif r <= 60: rarity, stars, color = "Legendario", "⭐⭐⭐⭐", discord.Color.brand_red()
        elif r <= 200: rarity, stars, color = "Épico", "⭐⭐⭐", discord.Color.purple()
        elif r <= 500: rarity, stars, color = "Raro", "⭐⭐", discord.Color.blue()
        else: rarity, stars, color = "Común", "⭐", discord.Color.light_grey()
        
        await db.execute("INSERT INTO gacha_collection (guild_id, user_id, character_name, rarity, image_url) VALUES (?, ?, ?, ?, ?)", (ctx.guild.id, ctx.author.id, char_name, rarity, img_url))
        
        embed = discord.Embed(title="🎰 Invocación Gacha", description=f"¡Has conseguido a **{char_name}**!\n\n**Rareza:** {rarity} {stars}", color=color)
        if img_url: embed.set_image(url=img_url)
        embed.set_footer(text=f"-{apuesta} {emoji_currency} cobrados de tu cartera")
        await ctx.send(embed=embed)

    @gacha.command(name="list", aliases=['collection'], description="Muestra tu colección de personajes del gacha.")
    async def gacha_list(self, ctx: commands.Context):
        chars = await db.fetchall("SELECT character_name, rarity FROM gacha_collection WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, ctx.author.id))
        if not chars: return await ctx.send("❌ No tienes ningún personaje en tu colección. Usa `/gacha pull`.", ephemeral=True)
        
        counts = {"Mítico": [], "Legendario": [], "Épico": [], "Raro": [], "Común": []}
        for c in chars:
            counts[c['rarity']].append(c['character_name'])
            
        embed = discord.Embed(title=f"📚 Colección Gacha de {ctx.author.display_name}", color=self.bot.CREAM_COLOR)
        embed.description = f"Personajes totales: **{len(chars)}**"
        for r, lst in counts.items():
            if lst:
                show = ", ".join(lst[:8]) + (f" (y {len(lst)-8} más)" if len(lst) > 8 else "")
                embed.add_field(name=f"{r} ({len(lst)})", value=show, inline=False)
                
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="trivia", description="Responde una pregunta de cultura pop/anime más rápido para ganar un premio de monedas.")
    @commands.cooldown(1, 30, commands.BucketType.guild)
    async def trivia(self, ctx: commands.Context):
        # Anime trivia open db
        url = "https://opentdb.com/api.php?amount=1&category=31&type=multiple"
        try:
            async with self.bot.http_session.get(url) as resp:
                data = await resp.json()
                if data['response_code'] != 0: return await ctx.send("No pude obtener los archivos de la trivia maestra. Prueba en un momento.")
                q_data = data['results'][0]
        except Exception as e:
            return await ctx.send(f"❌ Error conectando a la base de datos de trivia: {e}")
            
        question = html.unescape(q_data['question'])
        correct = html.unescape(q_data['correct_answer'])
        options = [html.unescape(o) for o in q_data['incorrect_answers']] + [correct]
        random.shuffle(options)
        
        settings = await db.get_guild_economy_settings(ctx.guild.id)
        emoji = settings.get('currency_emoji', '🪙')
        prize = random.randint(150, 400)
        
        embed = discord.Embed(title="🧠 Trivia de Rapidez", description=f"**{question}**\n\nPremio estipulado: **{prize}** {emoji}", color=discord.Color.teal())
        
        view = TriviaView(ctx, self, correct, prize)
        for i, opt in enumerate(options):
            lbl = opt[:77] + "..." if len(opt) > 80 else opt
            view.children[i].label = lbl
            
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @commands.hybrid_command(name="setup_confessions", description="Coloca el panel interactivo de confesiones anónimas en este canal (Admin).")
    @commands.has_permissions(administrator=True)
    async def setup_confessions(self, ctx: commands.Context):
        embed = discord.Embed(title="📮 Buzón de Confesiones", description="¿Tienes un secreto oscuro? ¿Un mensaje para alguien en el servidor? Exprésalo de forma segura y 100% anónima.\n\n**Oprime el botón abajo para abrir el confesionario privado.** Nadie sabrá tu identidad.", color=self.bot.CREAM_COLOR)
        await ctx.send(embed=embed, view=ConfessView())
        await ctx.message.delete()

async def setup(bot: commands.Bot):
    # Registrar las vistas persistentes
    bot.add_view(ConfessView())
    await bot.add_cog(FunCog(bot))
