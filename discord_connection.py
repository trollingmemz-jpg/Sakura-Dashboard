"""Optional read-only Discord bot integration. No user tokens, message history or disk logs."""
import asyncio,threading
class DiscordConnection:
 def __init__(self):
  self.state={'status':'Disconnected','voice':[],'messages':[]};self.client=None;self.loop=None;self.generation=0
 def disconnect(self):
  self.generation+=1
  client,loop=self.client,self.loop
  self.client=None;self.loop=None
  if client and loop and loop.is_running():asyncio.run_coroutine_threadsafe(client.close(),loop)
  self.state={'status':'Disconnected','voice':[],'messages':[]}
 def connect(self,token,user_id,guild_id,channel_id):
  self.disconnect();gen=self.generation
  self.state={'status':'Connecting…','voice':[],'messages':[]}
  def work():
   try:
    import discord
    async def run():
     intents=discord.Intents.none();intents.guilds=True;intents.voice_states=True
     intents.guild_messages=bool(channel_id);intents.message_content=bool(channel_id)
     client=discord.Client(intents=intents)
     if gen!=self.generation:return
     self.client=client;self.loop=asyncio.get_running_loop()
     def publish(**data):
      if gen==self.generation:self.state={**self.state,**data}
     def voice():
      guild=client.get_guild(guild_id)
      if not guild:publish(status='Bot is not in the selected server',voice=[]);return
      channel=next((c for c in guild.voice_channels+guild.stage_channels if user_id in c.voice_states),None)
      members=[]
      if channel:
       for uid,v in channel.voice_states.items():
        m=guild.get_member(uid)
        members.append((m.display_name if m else str(uid),bool(v.mute or v.self_mute),bool(v.deaf or v.self_deaf)))
      publish(status='Connected • '+guild.name,channel=channel.name if channel else '',voice=members)
     @client.event
     async def on_ready():voice()
     @client.event
     async def on_voice_state_update(member,before,after):
      if member.guild.id==guild_id:voice()
     @client.event
     async def on_message(message):
      if message.guild and message.guild.id==guild_id and message.channel.id==channel_id:
       publish(messages=(self.state.get('messages',[])+[(message.author.display_name,message.content[:500])])[-20:])
     async with client:await client.start(token)
    asyncio.run(run())
   except ImportError:
    if gen==self.generation:self.state={'status':'Discord module is not installed','voice':[],'messages':[]}
   except Exception:
    if gen==self.generation:self.state={'status':'Discord connection failed. Check bot token, permissions and intents.','voice':[],'messages':[]}
  threading.Thread(target=work,daemon=True).start()
