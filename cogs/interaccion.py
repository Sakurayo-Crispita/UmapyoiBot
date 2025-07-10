import discord
from discord.ext import commands
import aiohttp
import random

class InteractionCog(commands.Cog, name="Interacción"):
    """Comandos para interactuar con otros usuarios."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Función para obtener GIFs interactivos ---
    async def get_interactive_gif(self, ctx: commands.Context, target: discord.Member, category: str, action_templates: list[str], color: discord.Color):
        await ctx.defer(ephemeral=False)
        
        if ctx.author == target and category not in ["baka"]:
            await ctx.send("No puedes realizar esta acción contigo mismo.", ephemeral=True)
            return

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"https://api.waifu.pics/sfw/{category}") as response:
                    if response.status == 200:
                        data = await response.json()
                        gif_url = data.get("url")
                        if gif_url:
                            action_text = random.choice(action_templates).format(
                                author=ctx.author.mention,
                                target=target.mention
                            )
                            
                            embed = discord.Embed(description=action_text, color=color)
                            embed.set_image(url=gif_url)
                            await ctx.send(embed=embed)
                        else:
                            await ctx.send("No se pudo obtener un GIF.", ephemeral=True)
                    else:
                        await ctx.send(f"Error al contactar la API (Estado: {response.status}).", ephemeral=True)
            except Exception as e:
                print(f"Error en el comando interactivo {category}: {e}")
                await ctx.send("Ocurrió un error inesperado.", ephemeral=True)

    # --- Comandos Interactivos (SFW) ---
    
    @commands.hybrid_command(name="kiss", description="Besa a otro usuario.")
    async def kiss(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} le dio un tierno beso a {target}.",
            "¡Un beso robado! {author} acaba de besar a {target}.",
            "Los labios de {author} y {target} se encontraron en un dulce beso.",
            "{author} se acercó y le plantó un beso suave a {target}.",
            "Un momento mágico: {author} besó a {target} con ternura.",
            "{target} se sonrojó después de recibir un beso de {author}.",
            "¡Qué romántico! {author} y {target} compartieron un beso.",
            "{author} no pudo resistirse y besó a {target}.",
            "El aire se llenó de chispas cuando {author} besó a {target}.",
            "Un 'muak' de {author} para {target}.",
            "{author} le da un beso en la mejilla a {target}.",
            "¡El amor está en el aire! {author} besa a {target}."
        ]
        await self.get_interactive_gif(ctx, miembro, "kiss", action_phrases, discord.Color.magenta())

    @commands.hybrid_command(name="cuddle", description="Acurrúcate con otro usuario.")
    async def cuddle(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} se acurrucó tiernamente con {target}.",
            "{author} y {target} están en un abrazo muy cercano.",
            "¡Qué momento tan tierno! {author} está abrazando a {target}.",
            "Nada como un buen acurrucamiento entre {author} y {target}.",
            "{author} encontró consuelo en los brazos de {target}.",
            "Es hora de acurrucarse, y {author} eligió a {target}.",
            "{author} y {target} se acurrucan juntos para ver una película.",
            "¡Aww! {author} y {target} son la definición de tierno."
        ]
        await self.get_interactive_gif(ctx, miembro, "cuddle", action_phrases, discord.Color.green())

    @commands.hybrid_command(name="hug", description="Dale un abrazo a otro usuario.")
    async def hug(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} le dio un gran abrazo a {target}.",
            "{target} recibió un cálido abrazo de {author}.",
            "{author} rodeó a {target} con sus brazos en un abrazo.",
            "¡Abrazo grupal! Bueno, solo entre {author} y {target} por ahora.",
            "Un abrazo de oso de {author} para {target}.",
            "{author} le ofrece un abrazo reconfortante a {target}.",
            "¡Necesitabas un abrazo! {author} está aquí para {target}.",
            "Los problemas se van con un abrazo de {author} a {target}."
        ]
        await self.get_interactive_gif(ctx, miembro, "hug", action_phrases, discord.Color.teal())

    @commands.hybrid_command(name="pat", description="Dale una palmadita en la cabeza a alguien.")
    async def pat(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "{author} le dio unas palmaditas en la cabeza a {target}. ¡Qué tierno!",
            "{target} recibió unas suaves palmaditas de {author}.",
            "¡Buen chico/a! {author} acaricia la cabeza de {target}.",
            "Una palmadita de aprobación de {author} para {target}.",
            "{author} le muestra su afecto a {target} con una palmadita.",
            "Pat, pat, pat... {author} consuela a {target}.",
            "{target} ronronea (o casi) por las palmaditas de {author}."
        ]
        await self.get_interactive_gif(ctx, miembro, "pat", action_phrases, discord.Color.gold())

    @commands.hybrid_command(name="slap", description="Dale una bofetada a alguien.")
    async def slap(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "¡ZAS! {author} le dio una bofetada a {target}.",
            "{target} sintió la mano de {author} en su mejilla.",
            "Parece que {target} se lo merecía... {author} le dio una cachetada.",
            "¡Auch! Esa bofetada de {author} a {target} debió doler.",
            "{author} le dejó la cara roja a {target} con una bofetada.",
            "¡Toma! {author} le da una bofetada a {target} por pasarse de listo.",
            "Una bofetada correctiva de {author} para {target}.",
            "En toda la cara. {author} abofeteó a {target}."
        ]
        await self.get_interactive_gif(ctx, miembro, "slap", action_phrases, discord.Color.orange())

    @commands.hybrid_command(name="tickle", description="Hazle cosquillas a alguien.")
    async def tickle(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "¡Guerra de cosquillas! {author} le hace cosquillas a {target}.",
            "{target} no puede parar de reír por las cosquillas de {author}.",
            "{author} encontró el punto débil de {target} y ahora le hace cosquillas sin parar.",
            "¡Cosquillas, cosquillas! {author} ataca a {target}.",
            "{target} se retuerce de la risa. ¡Culpa de {author}!"
        ]
        await self.get_interactive_gif(ctx, miembro, "tickle", action_phrases, discord.Color.light_grey())

    @commands.hybrid_command(name="poke", description="Pica a alguien para llamar su atención.")
    async def poke(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "¡Oye! {author} le dio un toquecito a {target}.",
            "{author} pica a {target}. ¿Qué querrá?",
            "Un 'poke' de {author} para {target}.",
            "Hey, {target}, {author} te está molestando.",
            "Poke, poke, poke... {author} no dejará en paz a {target}."
        ]
        await self.get_interactive_gif(ctx, miembro, "poke", action_phrases, discord.Color.dark_blue())

    @commands.hybrid_command(name="baka", description="Llama 'baka' a alguien.")
    async def baka(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "¡BAKA! {author} le grita a {target}.",
            "{author} piensa que {target} es un completo baka.",
            "No es que me gustes ni nada, {target}... ¡Baka! - Atte. {author}",
            "¿Eres tonto o qué, {target}? ¡Baka! Dice {author}.",
            "{author} suspira... 'Yare yare, {target} es un baka'.",
            "La paciencia de {author} se agota. '¡BAKA, {target}!'",
            "{author} te señala, {target}, y declara: '¡Un idiota!'.",
            "A veces, la única palabra que {author} tiene para {target} es... BAKA.",
            "Tsundere mode on: {author} mira a {target} y susurra '...baka'."
        ]
        await self.get_interactive_gif(ctx, miembro, "baka", action_phrases, discord.Color.dark_red())

    @commands.hybrid_command(name="highfive", description="Choca esos cinco con alguien.")
    async def highfive(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "¡Choca esos cinco! {author} y {target} celebran.",
            "{author} le da un high five a {target}. ¡Buen trabajo!",
            "¡Arriba esas manos! {author} choca con {target}."
        ]
        await self.get_interactive_gif(ctx, miembro, "highfive", action_phrases, [], discord.Color.blue())

    @commands.hybrid_command(name="bonk", description="Envía a alguien a la cárcel de los hornys.")
    async def bonk(self, ctx: commands.Context, miembro: discord.Member):
        action_phrases = [
            "¡BONK! {author} envía a {target} a la cárcel de los hornys.",
            "{author} le da un golpe a {target} con el bate anti-horny.",
            "{target} ha sido bonkeado por {author}. ¡A la esquina!",
            "Se escuchó un 'bonk' a lo lejos. {author} encontró a {target}."
        ]
        await self.get_interactive_gif(ctx, miembro, "bonk", action_phrases, [], discord.Color.dark_gold())

    @commands.hybrid_command(name="blush", description="Sonrójate por alguien o por algo.")
    async def blush(self, ctx: commands.Context, por: Optional[discord.Member] = None):
        action_phrases = [
            "{author} se sonroja por culpa de {target}.",
            "¡Mira lo que hiciste, {target}! {author} está todo rojo.",
            "{author} no puede evitar sonrojarse al ver a {target}."
        ]
        self_action_phrases = [
            "{author} se sonrojó.",
            "{author} se puso rojo como un tomate.",
            "Algo hizo que {author} se sonrojara."
        ]
        await self.get_interactive_gif(ctx, por, "blush", action_phrases, self_action_phrases, discord.Color.from_rgb(255, 182, 193)) # Rosa claro

async def setup(bot: commands.Bot):
    await bot.add_cog(InteractionCog(bot))
