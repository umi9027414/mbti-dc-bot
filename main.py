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

from dotenv import load_dotenv
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
print(f"TOKEN is: {TOKEN}")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

user_sessions = {}  # 每位使用者的測驗資料

@bot.command()
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

    # 初始化使用者資料
    questions = []
    for func, items in function_questions.items():
        shuffled = items.copy()
        import random
        random.shuffle(shuffled)
        for q in shuffled:
            questions.append((func, q))
    random.shuffle(questions)

    user_sessions[user.id] = {
        "index": 0,
        "scores": {f: 0 for f in function_questions},
        "questions": questions,
        "start_time": now,
        "guild_id": ctx.guild.id
    }

    await user.send(
        f"🧪 **MBTI 八功能測驗啟動**\n"
        f"每題的作答都不牽涉人際、利益、優劣、得失，用你最喜歡的方式作答才會做出最準確的結果。\n"
        f"🔢 分數範圍為：1（完全不同意）～ 5（非常同意）\n"
        f"📝 本測驗共 {len(questions)} 題，請依序作答。"
    )
    await send_next_question(user)

async def send_next_question(user):
    session = user_sessions[user.id]
    index = session["index"]
    questions = session["questions"]
    if index >= len(questions):
        await finalize_test(user)
        return

    func, (poetic, plain) = questions[index]
    view = View()
 # ✅ 分數按鈕
    for score in range(1, 6):
        async def make_callback(score=score):
            async def callback(interaction: Interaction):
                session["scores"][func] += score
                session["index"] += 1
                await interaction.response.edit_message(
                    content=(
                        f"✅ 已紀錄：你給了 {score} 分。\n"
                        f"📖 第 {index + 1} / {len(questions)} 題：\n"
                        f"{poetic}"
                    ),
                    view=None
                )
                await asyncio.sleep(1)
                await send_next_question(user)
            return callback

        btn = Button(label=str(score), style=ButtonStyle.primary)
        btn.callback = await make_callback()
        view.add_item(btn)
 # ✅ 切換描述按鈕：建立兩個函式切換 view 文字

    async def show_plain(interaction: Interaction):
        await interaction.response.edit_message(
            content=f"**（簡潔版）第 {index + 1} / {len(questions)} 題：** {plain}",
            view=view_plain
        )

    async def show_poetic(interaction: Interaction):
        await interaction.response.edit_message(
            content=f"**第 {index + 1} 題：** {poetic}",
            view=view
        )

    # 原始 view 加上「查看簡潔版」按鈕
    plain_btn = Button(label="查看簡潔版", style=ButtonStyle.secondary)
    plain_btn.callback = show_plain
    view.add_item(plain_btn)

    # 簡潔版 view 加上「切回詩意版」按鈕
    view_plain = View()
    for score in range(1, 6):
        btn = Button(label=str(score), style=ButtonStyle.primary)
        btn.callback = await make_callback(score)
        view_plain.add_item(btn)

    poetic_btn = Button(label="切回詩意版", style=ButtonStyle.secondary)
    poetic_btn.callback = show_poetic
    view_plain.add_item(poetic_btn)

    # 發送第一題（詩意版）
    await user.send(f"**第 {index + 1} 題**：{poetic}", view=view)

def calculate_mbti_by_axis(scores):
    sorted_funcs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_funcs = [f for f, _ in sorted_funcs[:4]]
    is_extroverted_dominant = top_funcs[0] in ["Fe", "Te", "Ne", "Se"]

    perceiving_axis = "N" if scores["Ne"] + scores["Ni"] > scores["Se"] + scores["Si"] else "S"
    judging_axis = "T" if scores["Te"] + scores["Ti"] > scores["Fe"] + scores["Fi"] else "F"

    if is_extroverted_dominant:
        jp = "J" if top_funcs[0] in ["Fe", "Te"] else "P"
    else:
        jp = "J" if top_funcs[1] in ["Fe", "Te"] else "P"

    ei = "E" if is_extroverted_dominant else "I"
    return ei + perceiving_axis + judging_axis + jp, top_funcs[0]

async def finalize_test(user):
    session = user_sessions[user.id]
    scores = session["scores"]
    mbti_type, dominant_func = calculate_mbti_by_axis(scores)

    user_test_history[str(user.id)] = session["start_time"].isoformat()
    with open("user_test_history.json", "w", encoding="utf-8") as f:
        json.dump(user_test_history, f, indent=2)

    guild = bot.get_guild(session["guild_id"])
    member = guild.get_member(user.id)
    await assign_mbti_role(member, guild, mbti_type)
    await send_result_embed(user, mbti_type, dominant_func)

    # 顯示八功能排序結果
    sorted_funcs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    ranking_text = "\n".join([f"{i+1}. {func}" for i, (func, _) in enumerate(sorted_funcs)])

    await user.send(
        "**🧩 你的八功能排序結果如下（不含分數）**\n"
    f"{ranking_text}\n\n"
    "（本排序代表你在本次測驗中傾向使用的認知方式，僅供參考。）"
    )    

    await send_mbti_stats(user, guild)

async def assign_mbti_role(member, guild, mbti_type):
    mbti_roles = ["INTJ", "INTP", "ENTJ", "ENTP", "INFJ", "INFP", "ENFJ", "ENFP",
                  "ISTJ", "ISFJ", "ESTJ", "ESFJ", "ISTP", "ISFP", "ESTP", "ESFP"]
    existing_roles = [r for r in member.roles if r.name in mbti_roles]
    for r in existing_roles:
        await member.remove_roles(r)
    role = discord.utils.get(guild.roles, name=mbti_type)
    if not role:
        role = await guild.create_role(name=mbti_type)
    await member.add_roles(role)

async def send_result_embed(user, mbti_type, dominant_func):
    descriptions = {
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
        description=f"{descriptions.get(mbti_type, '')}\n\n🔧 主導功能：{dominant_func} — {func_desc.get(dominant_func, '')}",
        color=discord.Color.purple()
    )
    await user.send(embed=embed)

async def send_mbti_stats(user, guild):
    result = {}
    for role in guild.roles:
        if role.name in ["INTJ", "INTP", "ENTJ", "ENTP", "INFJ", "INFP", "ENFJ", "ENFP",
                         "ISTJ", "ISFJ", "ESTJ", "ESFJ", "ISTP", "ISFP", "ESTP", "ESFP"]:
            result[role.name] = len(role.members)
    text = "\n".join(f"- {k}：{v}人" for k, v in sorted(result.items()))
    await user.send(f"📊 **目前伺服器 MBTI 分布：**\n{text}")

@bot.event
async def on_ready():
    print(f'✅ Bot is ready. Logged in as {bot.user}')

bot.run(TOKEN)