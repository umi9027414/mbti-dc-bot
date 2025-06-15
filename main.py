import os
import discord
from discord.ext import commands
from discord import ButtonStyle, Interaction
from discord.ui import View, Button
from dotenv import load_dotenv
import asyncio
import json
from datetime import datetime, timedelta

# 讀取題庫與歷史紀錄
with open("function_questions.json", "r", encoding="utf-8") as f:
    function_questions = json.load(f)
try:
    with open("user_test_history.json", "r", encoding="utf-8") as f:
        user_test_history = json.load(f)
except FileNotFoundError:
    user_test_history = {}

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

user_sessions = {}

@bot.command(name="start_test", aliases=["mbti", "測驗"])
async def start_test(ctx):
    user = ctx.author
    if not isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("📬 測驗將透過私訊進行，請查看你的 DM 收件匣。")
    now = datetime.utcnow()
    uid = str(user.id)
    if uid in user_test_history:
        last_time = datetime.fromisoformat(user_test_history[uid])
        if now < last_time + timedelta(days=30):
            next_allowed = last_time + timedelta(days=30)
            await user.send(
                f"⏳ 你已於 {last_time.date()} 測驗過，請於 {next_allowed.date()} 再次測驗。"
            )
            return
    # 初始化測驗資料
    import random
    questions = [(func, q) for func, lst in function_questions.items() for q in lst]
    random.shuffle(questions)
    user_sessions[user.id] = {
        "index": 0,
        "scores": {f: 0 for f in function_questions},
        "questions": questions,
        "start_time": now,
        "guild_id": ctx.guild.id if ctx.guild else None,
    }
    await user.send(
        "🧪 **MBTI 八功能測驗啟動**\n"
        "每題的作答都不牽涉人際、利益、優劣、得失，用你最喜歡的方式作答才會做出最準確的結果。\n"
        "🔢 分數範圍為：1（完全不同意）～ 5（非常同意）\n"
        f"📝 本測驗共 {len(questions)} 題，請依序作答。"
    )
    await send_next_question(user)

async def send_next_question(user):
    session = user_sessions.get(user.id)
    if not session:
        return
    index = session["index"]
    questions = session["questions"]
    if index >= len(questions):
        await finalize_test(user)
        return
    func, (poetic, plain) = questions[index]
    view = View(timeout=None)
    async def make_callback(score):
        async def callback(interaction: Interaction):
            if user_sessions[user.id]["index"] != index:
                return
            session["scores"][func] += score
            session["index"] += 1
            await interaction.response.edit_message(
                content=f"✅ 已紀錄：你給了 {score} 分。\n📖 第 {index + 1} / {len(questions)} 題：\n{poetic}",
                view=None,
            )
            await asyncio.sleep(0.5)
            await send_next_question(user)
        return callback

    for score in range(1, 6):
        btn = Button(label=str(score), style=ButtonStyle.primary)
        btn.callback = await make_callback(score)
        view.add_item(btn)

    # 顯示簡潔版按鈕
    async def show_plain(interaction: Interaction):
        await interaction.response.edit_message(
            content=f"📘 第 {index + 1} 題：{plain}", view=view_plain
        )

    view_plain = View(timeout=None)
    for score in range(1, 6):
        btn = Button(label=str(score), style=ButtonStyle.primary)
        btn.callback = await make_callback(score)
        view_plain.add_item(btn)
    btn_back = Button(label="切回詩意版", style=ButtonStyle.secondary)
    btn_back.callback = lambda i: i.response.edit_message(
        content=f"📖 第 {index + 1} 題：{poetic}", view=view
    )
    view_plain.add_item(btn_back)

    btn_plain = Button(label="查看簡潔版", style=ButtonStyle.secondary)
    btn_plain.callback = show_plain
    view.add_item(btn_plain)

    await user.send(f"📖 第 {index + 1} 題：{poetic}", view=view)

def calculate_mbti_by_axis(scores):
    # 相對排序：將功能依得分排序
    sorted_funcs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_funcs_raw = [f for f, _ in sorted_funcs]

    # 定義功能對立組合（互斥）
    opposing_pairs = [("Ne", "Se"), ("Ni", "Si"), ("Te", "Fe"), ("Ti", "Fi")]

    # 移除 top 4 中出現的對立功能（保留得分高的）
    top_funcs = []
    seen_opposites = set()
    for func in top_funcs_raw:
        for a, b in opposing_pairs:
            if func == a and b in top_funcs:
                break
            if func == b and a in top_funcs:
                break
        else:
            top_funcs.append(func)
        if len(top_funcs) == 4:
            break

    # 根據功能組合穩定度，從 top 4 推測 MBTI 類型
    # 建立代表性組合與對應 MBTI 類型
    mbti_by_stack = {
        ("Ni", "Te"): "INTJ",
        ("Te", "Ni"): "ENTJ",
        ("Ne", "Ti"): "ENTP",
        ("Ti", "Ne"): "INTP",
        ("Si", "Fe"): "ISFJ",
        ("Fe", "Si"): "ESFJ",
        ("Fi", "Se"): "ISFP",
        ("Se", "Fi"): "ESFP",
        ("Fi", "Ni"): "INFP",
        ("Ni", "Fi"): "INFJ",
        ("Fe", "Ne"): "ENFJ",
        ("Ne", "Fe"): "ENFP",
        ("Ti", "Si"): "ISTP",
        ("Si", "Ti"): "ISTJ",
        ("Te", "Se"): "ESTJ",
        ("Se", "Te"): "ESTP"
    }

    # 嘗試從 top 2 或 top 3 中推導
    mbti_type = "XXXX"
    for length in [2, 3]:
        for i in range(len(top_funcs) - length + 1):
            key = tuple(top_funcs[i:i+2])
            if key in mbti_by_stack:
                mbti_type = mbti_by_stack[key]
                break
        if mbti_type != "XXXX":
            break

    return mbti_type, top_funcs

async def finalize_test(user):
    session = user_sessions[user.id]
    scores = session["scores"]
    mbti_type, top_funcs = calculate_mbti_by_axis(scores)
    user_test_history[str(user.id)] = session["start_time"].isoformat()
    with open("user_test_history.json", "w", encoding="utf-8") as f:
        json.dump(user_test_history, f, indent=2)

    guild = bot.get_guild(session["guild_id"])
    if guild:
        member = guild.get_member(user.id)
        await assign_mbti_role(member, guild, mbti_type)
        await send_mbti_stats(user, guild)
    await send_result_embed(user, mbti_type, top_funcs[0], top_funcs)

async def assign_mbti_role(member, guild, mbti_type):
    mbti_roles = ["INTJ", "INTP", "ENTJ", "ENTP", "INFJ", "INFP", "ENFJ", "ENFP",
                  "ISTJ", "ISFJ", "ESTJ", "ESFJ", "ISTP", "ISFP", "ESTP", "ESFP"]
    for r in member.roles:
        if r.name in mbti_roles:
            await member.remove_roles(r)
    role = discord.utils.get(guild.roles, name=mbti_type)
    if not role:
        role = await guild.create_role(name=mbti_type)
    await member.add_roles(role)

async def send_result_embed(user, mbti_type, dom_func, func_rank):
    descs = {
        "INTJ": "你預見未來、堅持原則，是寂靜中的建築師。",
        "INTP": "你追尋真理，理性又充滿好奇，是知識的探索者。",
        "ENTJ": "你統御未來，以理智驅動行動，是天生的指揮官。",
        "ENTP": "你創意無限，辯證靈活，是點子與挑戰的遊俠。",
        "INFJ": "你擁有深邃直覺與溫柔理想，是願景的守望者。",
        "INFP": "你的內在如詩，敏感卻堅定，是靈魂的照護者。",
        "ENFJ": "你以關懷引領群體，是人際連結的靈魂之光。",
        "ENFP": "你熱情洋溢、想像力豐富，是世界的探索家。",
        "ISTJ": "你嚴謹可靠，是秩序與責任的實踐者。",
        "ISFJ": "你溫和細心，是傳統與關懷的庇護者。",
        "ESTJ": "你務實強勢，是行動與規則的執行者。",
        "ESFJ": "你關心每個人，是團體氛圍的守護者。",
        "ISTP": "你冷靜靈巧，是解決問題的工程師。",
        "ISFP": "你安靜自由，是自然與藝術的愛好者。",
        "ESTP": "你果斷敏捷，是現場即興的冒險家。",
        "ESFP": "你活力四射，是生活舞台上的明星。"
    }
    func_desc = {
        "Fi": "你擁有強烈的內在價值系統，為自己而活。",
        "Fe": "你擅長理解並調節群體中的情感能量。",
        "Ti": "你以邏輯為劍，剖析世界的每一道結構。",
        "Te": "你以效率與規劃改造現實，讓混沌有序。",
        "Ni": "你仰望未來，預感真相尚未成形。",
        "Ne": "你靈光乍現，點子如繁星般閃耀不停。",
        "Si": "你珍藏過往，用記憶建立對世界的信任。",
        "Se": "你活在當下，敏銳感知每一分真實刺激。"
    }
    embed = discord.Embed(
        title=f"🌟 你的 MBTI 類型是 {mbti_type}",
        description=f"{descs.get(mbti_type)}\n\n🔧 主導功能：{dom_func} — {func_desc.get(dom_func)}",
        color=discord.Color.purple()
    )
    embed.add_field(name="📊 你的陽面功能排序", value=" → ".join(func_rank), inline=False)
    await user.send(embed=embed)

async def send_mbti_stats(user, guild):
    result = {}
    for role in guild.roles:
        if role.name in ["INTJ", "INTP", "ENTJ", "ENTP", "INFJ", "INFP", "ENFJ", "ENFP",
                         "ISTJ", "ISFJ", "ESTJ", "ESFJ", "ISTP", "ISFP", "ESTP", "ESFP"]:
            result[role.name] = len(role.members)
    text = "\\n".join(f"- {k}：{v}人" for k, v in sorted(result.items()))
    await user.send(f"📊 **目前伺服器 MBTI 分布：**\\n{text}")

@bot.event
async def on_ready():
    print(f'✅ Bot is ready. Logged in as {bot.user}')

bot.run(TOKEN)