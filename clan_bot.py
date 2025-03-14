from flask import *
from flask_sqlalchemy import SQLAlchemy
import discord
from discord.ext import commands
from discord.ui import Button, View
from discord import utils
import asyncio
from settings import *
import time
from datetime import datetime, timedelta
import pytz
from sqlalchemy import Column, Integer, String, ForeignKey
import random
from collections import defaultdict
import json
import os
import logging

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = r"sqlite:///mydatabase.bd"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

logging.basicConfig(level=logging.ERROR)

class Clans(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    reputation = db.Column(db.Integer, default=0)
    clan_role_id = db.Column(db.String(100), nullable=False)
    clan_members = db.Column(db.Integer, default=0)

    quests = db.relationship('WeeklyClanQuest', back_populates='clan', cascade='all, delete-orphan')
    always_quests = db.relationship('AlwaysQuest', back_populates='clan', cascade='all, delete-orphan')

class WeeklyClanQuest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clan_id = db.Column(db.Integer, db.ForeignKey('clans.id', ondelete='CASCADE'), nullable=False)
    messages_sent = db.Column(db.Integer, default=0)
    voice_time = db.Column(db.Integer, default=0)
    completed = db.Column(db.Boolean, default=False)
    last_reset_timestamp = db.Column(db.Integer, default=0)

    clan = db.relationship('Clans', back_populates='quests')

class AlwaysQuest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clan_id = db.Column(db.Integer, db.ForeignKey('clans.id', ondelete='CASCADE'), nullable=False)
    messages_sent = db.Column(db.Integer, default=0)
    voice_time = db.Column(db.Integer, default=0)
    completed = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, nullable=False)
    task = db.Column(db.String(50))
    clan = db.relationship('Clans', back_populates='always_quests')

with app.app_context():
    db.create_all()

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

allowed_user = '1092934181979430932'
allowed_chanel = ''

def white_list(role_id):
    async def predicate(ctx):
        role = discord.utils.get(ctx.guild.roles, id=role_id)
        if role and role in ctx.author.roles:
            return True
        else:
            await ctx.send(f"У тебя нет роли `{role_id}`, чтобы использовать эту команду.")
            return False
    return commands.check(predicate)

def is_authorized_user():
    async def predicate(ctx):
        return ctx.author.id == 1092934181979430932
    return commands.check(predicate)


def is_allowed_channel_or_user(allowed_channel_id, allowed_user_id):
    async def predicate(ctx):
        return ctx.channel.id == allowed_channel_id or ctx.author.id == allowed_user_id
    return commands.check(predicate)

@bot.command()
@white_list(white_list_role_id)
async def обновить(ctx, role_mention=None):
    guild = ctx.guild

    with app.app_context():
        if role_mention:
            if not role_mention.startswith("<@&") or not role_mention.endswith(">"):
                await ctx.send("Пожалуйста, используйте правильный формат упоминания роли: <@&role_id>.")
                return

            role_id = int(role_mention[3:-1])
            role = guild.get_role(role_id)
            if not role:
                await ctx.send("Роль не найдена!")
                return

            count = sum(1 for member in guild.members if role in member.roles)
            clan = Clans.query.filter_by(clan_role_id=role_id).first()
            if not clan:
                await ctx.send(f"Клан с ролью ID {role_id} не найден!")
                return

            clan.clan_members = count
            db.session.commit()
            await ctx.send(f"Количество участников клана с ролью {role.name} обновлено на {count}.")
        else:
            clans = Clans.query.all()
            if not clans:
                await ctx.send("В базе данных нет кланов для обновления!")
                return

            updated_clans = []
            for clan in clans:
                role = guild.get_role(int(clan.clan_role_id))
                if not role:
                    continue

                count = sum(1 for member in guild.members if role in member.roles)
                clan.clan_members = count
                updated_clans.append(f"{role.name}: {count}")
                db.session.commit()

            if updated_clans:
                await ctx.send("Обновлены участники следующих кланов:\n" + "\n".join(updated_clans))
            else:
                await ctx.send("Не удалось найти роли для обновления участников.")



@bot.command()
@white_list(white_list_role_id)
async def клан(ctx):
    embed = discord.Embed(
        title='Главное меню по управлению кланами',
        description= 'Выбери, что хочешь сделать ниже нажав на кнопку',
        color=discord.Color.blue()
    )
    button1 = Button(label='✅Создать клан✅', style=discord.ButtonStyle.green, custom_id='button1')
    button2 = Button(label='📈Изменить клан📉', style=discord.ButtonStyle.primary, custom_id='button2')
    button3 = Button(label='❌Удалить клан❌', style=discord.ButtonStyle.danger, custom_id='button3')
    button4 = Button(label='Отмена действия', style=discord.ButtonStyle.gray, custom_id='button4')

    view = View()
    view.add_item(button1)
    view.add_item(button2)
    view.add_item(button3)
    view.add_item(button4)

    await ctx.send(embed=embed, view=view)

    async def button1_callback(interaction):
        await interaction.response.send_message('Пожалуйста, укажите роль для клана (тэг клана).')
        await interaction.message.delete()

        def check_role(message):
            return message.author == interaction.user and message.content.startswith("<@&")

        role_msg = await bot.wait_for('message', check=check_role)
        role_id = int(role_msg.content[3:-1])

        role = utils.get(interaction.guild.roles, id=role_id)
        if role:
            with app.app_context():
                clan_name = role.name
                member_count = sum(1 for member in interaction.guild.members if role in member.roles)


                new_clan = Clans(
                    name=clan_name,
                    clan_role_id=role_id,
                    clan_members=member_count
                )
                db.session.add(new_clan)
                db.session.commit()

            await interaction.followup.send(f"Клан с ролью **{role.name}** успешно создан! Количество участников: {member_count}")
        else:
            await interaction.followup.send("Роль не найдена! Убедитесь, что вы отправили правильный тэг.")

    async def button2_callback(interaction):
        await interaction.response.send_message('Выбери клан для изменения (тэг клана).')
        await interaction.message.delete()
        def check_role_tag(message):
            return message.author == interaction.user and message.content.startswith("<@&")
    
        try:
            msg = await bot.wait_for('message', check=check_role_tag, timeout=60)
        except asyncio.TimeoutError:
            await interaction.followup.send("Время ожидания истекло. Попробуйте снова.")
            return

        try:
            role_id = int(msg.content[3:-1])
        except ValueError:
            await interaction.followup.send("Неверный формат тега роли. Убедитесь, что вы указали правильный тег.")
            return

        guild = interaction.guild
        role = guild.get_role(role_id)
        if not role:
            await interaction.followup.send("Роль не найдена. Проверьте правильность указанного тега.")
            return

        with app.app_context():
            clan = Clans.query.filter_by(clan_role_id=role_id).first()
            if not clan:
                await interaction.followup.send(f"Клан с ролью **{role.name}** не найден.")
                return

        embed = discord.Embed(
            title='Подтверждение изменения',
            description=f"Вы уверены, что хотите изменить репутацию клана **{role.name}**?",
            color=discord.Color.blue()
        )

        confirm_button = discord.ui.Button(label="Да, изменить", style=discord.ButtonStyle.primary, custom_id="confirm_edit")
        cancel_button = discord.ui.Button(label="Отменить", style=discord.ButtonStyle.secondary, custom_id="cancel_edit")

        view = discord.ui.View()
        view.add_item(confirm_button)
        view.add_item(cancel_button)

        async def confirm_edit_callback(interaction):
            await interaction.message.delete()
            if interaction.user != msg.author:
                await interaction.response.send_message("Вы не можете изменить этот клан.")
                return

            await interaction.response.send_message(f"Введите новую репутацию для клана **{role.name}** (число):")

            def check_reputation_input(message):
                return message.author == interaction.user and message.content.isdigit()

            try:
                reputation_msg = await bot.wait_for('message', check=check_reputation_input, timeout=60)
                new_reputation = int(reputation_msg.content)
            except asyncio.TimeoutError:
                await interaction.followup.send("Время ожидания истекло. Попробуйте снова.")
                return

            with app.app_context():
                clan = Clans.query.filter_by(clan_role_id=role_id).first()
                if clan:
                    try:
                        clan.reputation = new_reputation
                        db.session.commit()
                        await interaction.followup.send(f"Репутация клана **{role.name}** успешно обновлена на {new_reputation}.")
                    except Exception as e:
                        await interaction.followup.send("Произошла ошибка при обновлении репутации. Попробуйте снова.")
                else:
                    await interaction.followup.send(f"Клан с ролью **{role.name}** не найден.")

        async def cancel_edit_callback(interaction):
            await interaction.message.delete()
            await interaction.response.send_message(f"Изменение репутации клана **{role.name}** отменено.")


        confirm_button.callback = confirm_edit_callback
        cancel_button.callback = cancel_edit_callback

        await interaction.followup.send(embed=embed, view=view)


    async def button3_callback(interaction):
        await interaction.message.delete()
        await interaction.response.send_message('Выбери клан для удаления(тэг клана).')

        def check(message):
            return message.author == interaction.user and message.content.startswith("<@&")
    
        msg = await bot.wait_for('message', check=check)
        role_id = int(msg.content[3:-1])

        role = utils.get(interaction.guild.roles, id=role_id)
        if role:
            with app.app_context():
                clan = Clans.query.filter_by(clan_role_id=role_id).first()
                if not clan:
                    await interaction.response.send_message(f"Клан с ролью {role.name} не найден!")
                    return
                
                embed = discord.Embed(
                    title='Подтверждение удаления',
                    description=f"Вы уверены, что хотите удалить клан **{role.name}**?",
                    color=discord.Color.red()
                )

                confirm_button = discord.ui.Button(label="Да, удалить", style=discord.ButtonStyle.danger, custom_id="confirm_delete")
                cancel_button = discord.ui.Button(label="Отменить", style=discord.ButtonStyle.secondary, custom_id="cancel_delete")
            
                view = discord.ui.View()
                view.add_item(confirm_button)
                view.add_item(cancel_button)

                async def confirm_delete_callback(interaction):
                    await interaction.message.delete()
                    if interaction.user != msg.author:
                        await interaction.response.send_message("Это не ваш клан для удаления!")

                    with app.app_context():
                        clan_to_delete = Clans.query.filter_by(clan_role_id=role_id).first()
                        if clan_to_delete:
                            db.session.delete(clan_to_delete)
                            db.session.commit()
                    
                            await interaction.response.send_message(f'Клан {role.name} успешно удален')

                        return

                    

                async def cancel_delete_callback(interaction):
                    await interaction.message.delete()
                    await interaction.response.send_message(f"Удаление клана {role.name} отменено.")

                confirm_button.callback = confirm_delete_callback
                cancel_button.callback = cancel_delete_callback
                
                try:
                    await interaction.followup.send(embed=embed, view=view)
                except discord.errors.InteractionResponded:
                    await interaction.followup.send("Взаимодействие уже завершено.")
        else:
            await interaction.response.send_message("Роль не найдена! Убедитесь, что вы отправили правильный тэг.")

        confirm_button.callback = confirm_delete_callback
        cancel_button.callback = cancel_delete_callback

    async def button4_callback(interaction):
        await interaction.message.delete()
        await interaction.response.send_message('Действие отменено.')

    button1.callback = button1_callback
    button2.callback = button2_callback
    button3.callback = button3_callback
    button4.callback = button4_callback

#ЕЖЕНЕДЕЛЬНЫЕ ЗАДАНИЯ НАЧИНАЮТСЯ ТУТ ВЕСЬ КОД ПОСЛЕ ЭТОГО НЕ ОЧЕНЬ ОТНОСИТСЯ К ПРЕДЫДУЩЕМУ КРЧ НАДО ВОДЫ СЮДА НАЛИТЬ ПРОСТО ДАБЫ ВИДЕТЬ
#ЕЖЕНЕДЕЛЬНЫЕ ЗАДАНИЯ НАЧИНАЮТСЯ ТУТ ВЕСЬ КОД ПОСЛЕ ЭТОГО НЕ ОЧЕНЬ ОТНОСИТСЯ К ПРЕДЫДУЩЕМУ КРЧ НАДО ВОДЫ СЮДА НАЛИТЬ ПРОСТО ДАБЫ ВИДЕТЬ
#ЕЖЕНЕДЕЛЬНЫЕ ЗАДАНИЯ НАЧИНАЮТСЯ ТУТ ВЕСЬ КОД ПОСЛЕ ЭТОГО НЕ ОЧЕНЬ ОТНОСИТСЯ К ПРЕДЫДУЩЕМУ КРЧ НАДО ВОДЫ СЮДА НАЛИТЬ ПРОСТО ДАБЫ ВИДЕТЬ
#ЕЖЕНЕДЕЛЬНЫЕ ЗАДАНИЯ НАЧИНАЮТСЯ ТУТ ВЕСЬ КОД ПОСЛЕ ЭТОГО НЕ ОЧЕНЬ ОТНОСИТСЯ К ПРЕДЫДУЩЕМУ КРЧ НАДО ВОДЫ СЮДА НАЛИТЬ ПРОСТО ДАБЫ ВИДЕТЬ
#ЕЖЕНЕДЕЛЬНЫЕ ЗАДАНИЯ НАЧИНАЮТСЯ ТУТ ВЕСЬ КОД ПОСЛЕ ЭТОГО НЕ ОЧЕНЬ ОТНОСИТСЯ К ПРЕДЫДУЩЕМУ КРЧ НАДО ВОДЫ СЮДА НАЛИТЬ ПРОСТО ДАБЫ ВИДЕТЬ

def get_moscow_time():
    moscow_tz = pytz.timezone('Europe/Moscow')
    moscow_time = datetime.now(moscow_tz)
    return moscow_time


@bot.event
async def on_ready():
    print(f"Бот запущен как {bot.user}")
    asyncio.create_task(check_weekly_quests())
    print('проверка на нед задание успешна')

async def check_weekly_quests():
    await bot.wait_until_ready()
    while not bot.is_closed():
        current_time = get_moscow_time()
        if current_time.weekday() == 0 and current_time.hour == 0:
            with app.app_context():
                one_week_ago_timestamp = current_time.timestamp() - 7 * 24 * 60 * 60
                old_quests = WeeklyClanQuest.query.filter(WeeklyClanQuest.last_reset_timestamp < one_week_ago_timestamp).all()
                for quest in old_quests:
                    db.session.delete(quest)
                db.session.commit()
                print(f"Удалены устаревшие задания: {len(old_quests)}")
                clans = Clans.query.all()
                for clan in clans:
                    last_quest = WeeklyClanQuest.query.filter_by(clan_id=clan.id).order_by(WeeklyClanQuest.last_reset_timestamp.desc()).first()
                    if not last_quest or (current_time.timestamp() - float(last_quest.last_reset_timestamp) >= 7 * 24 * 60 * 60):
                        new_quest = WeeklyClanQuest(
                            clan_id=clan.id,
                            messages_sent=0,
                            voice_time=0,
                            completed=False,
                            last_reset_timestamp=current_time.timestamp()
                        )
                        db.session.add(new_quest)
                        print(f"Новый квест для клана {clan.name} был создан.")

                db.session.commit()

        await asyncio.sleep(60)

def create_always_task(user, clan):
    can_drop_task = ['text', 'text']
    dropped_task = random.choice(can_drop_task)
    print(f"Выдано задание: {dropped_task}")

    with app.app_context():
        existing_quest = AlwaysQuest.query.filter_by(clan_id=clan.id, user_id=user.id, completed=False).first()
        if not existing_quest:
            new_quest = AlwaysQuest(
                clan_id=clan.id,
                user_id=user.id,
                messages_sent=0,
                voice_time=0,
                task=dropped_task,
                completed=False
            )
            db.session.add(new_quest)
            db.session.commit()
            print(f"Создано новое задание для пользователя {user.id} в клане {clan.name}.")
        else:
            print(f"У пользователя {user.id} уже есть активное задание.")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user = message.author
    clans_notified = set()

    with app.app_context():
        for role in user.roles:
            print(f"Проверяем роль: {role.name}")

            clan = Clans.query.filter_by(clan_role_id=role.id).first()
            if clan:
                print(f"Найден клан: {clan.name}")

                quest = AlwaysQuest.query.filter_by(clan_id=clan.id, user_id=user.id, completed=False).first()
                if quest:
                    if quest.task == 'text':
                        quest.messages_sent += 1
                        db.session.commit()
                        print(f'Личное задание: сообщения пользователя {user.id} обновлено: {quest.messages_sent}')
                        if quest.messages_sent >= 30:
                            quest.completed = True
                            clan.reputation += 10
                            db.session.commit()
                            await message.channel.send(f"Пользователь <@{user.id}> завершил личное задание!\nЕго клану было начислено 10 репутации в качестве награды")

                            db.session.delete(quest)
                            db.session.commit()
                            print(f"Личное задание для {user.id} завершено и удалено.")
                    elif quest.task == 'voice':
                        if quest.voice_time >= 600:
                            quest.completed = True
                            clan.reputation += 10
                            db.session.commit()
                            await message.channel.send(f"Пользователь <@{user.id}> завершил личное задание!\nЕго клану было начислено 10 репутации в качестве награды")
                            db.session.delete(quest)
                            db.session.commit()
                            print(f"Личное задание для {user.id} завершено и удалено.")
                else:
                    create_always_task(user, clan)

                weekly_quest = WeeklyClanQuest.query.filter_by(clan_id=clan.id, completed=False).first()
                if weekly_quest:
                    weekly_quest.messages_sent += 1
                    db.session.commit()
                    print(f"Количество сообщений обновлено: {weekly_quest.messages_sent}")
                    if weekly_quest.messages_sent >= 5000 and weekly_quest.voice_time >= 24 * 3600:
                        weekly_quest.completed = True
                        clan.reputation += 800
                        db.session.commit()
                        clans_notified.add(clan.id)
                        await message.channel.send(f"Клан <@&{role.id}> завершил еженедельное задание!")
                        await message.channel.send(f"Клану <@&{role.id}> начислено 800 репутации.")
                        db.session.delete(weekly_quest)
                        db.session.commit()
                        print(f"Еженедельное задание для {clan.name} завершено и удалено.")
                else:
                    print(f"Еженедельное задание для клана {clan.name} не найдено.")

    await bot.process_commands(message)


@bot.command()
@white_list(white_list_role_id)
async def роли(ctx):
    with app.app_context():
        clans = Clans.query.all()
        if not clans:
            await ctx.send("В базе данных нет кланов.")
            return

        embed = discord.Embed(
            title="ID ролей кланов",
            description="Список всех кланов и их связанных ролей",
            color=discord.Color.blue()
        )

        for clan in clans:
            embed.add_field(
                name=f"Клан: {clan.name}",
                value=f"Роль ID: {clan.clan_role_id}",
                inline=False
            )

        await ctx.send(embed=embed)


@bot.command()
@white_list(white_list_role_id)
async def прогресс(ctx):
    with app.app_context():
        clans = Clans.query.all()
        if not clans:
            await ctx.send("На данный момент нет зарегистрированных кланов.")
            return

        embed = discord.Embed(
            title="Прогресс Еженедельных заданий всех кланов",
            description="Текущее состояние выполнения заданий.",
            color=discord.Color.blue()
        )

        for clan in clans:
            weekly_quest = WeeklyClanQuest.query.filter_by(clan_id=clan.id, completed=False).first()
            if weekly_quest:
                progress_messages = weekly_quest.messages_sent
                progress_voice_time = weekly_quest.voice_time
                goal_messages = 5000
                goal_voice_time = 24 * 3600

                embed.add_field(
                    name=f"Клан: {clan.name}",
                    value=(
                        f"Сообщения: {progress_messages}/{goal_messages} ({progress_messages / goal_messages:.1%})\n"
                        f"Голосовой чат: {progress_voice_time // 3600}ч "
                        f"{(progress_voice_time % 3600) // 60}м/{goal_voice_time // 3600}ч "
                        f"({progress_voice_time / goal_voice_time:.1%})\n"
                        f"Статус: {'Завершено' if weekly_quest.completed else 'В процессе'}"
                    ),
                    inline=False
                )
            else:
                embed.add_field(
                    name=f"Клан: {clan.name}",
                    value="Нет активного еженедельного задания.",
                    inline=False
                )

        await ctx.send(embed=embed)


@bot.command()
@white_list(white_list_role_id)
async def время(ctx):
    with app.app_context():
        clans = db.session.query(Clans, WeeklyClanQuest).join(
            WeeklyClanQuest, Clans.id == WeeklyClanQuest.clan_id
        ).filter(WeeklyClanQuest.completed == False).all()

        if not clans:
            await ctx.send("Нет активных недельных заданий для кланов.")
            return

        embed = discord.Embed(
            title="Время войса кланов для недельного задания",
            description="Список кланов с их текущим временем в голосовых каналах.",
            color=discord.Color.blue()
        )

        for clan, quest in clans:
            embed.add_field(
                name=f"Клан: {clan.name}",
                value=f"Время в войсе: {quest.voice_time}",
                inline=False
            )

        await ctx.send(embed=embed)

@bot.command()
@white_list(white_list_role_id)
async def установить_войс(ctx, clan_role_id: int, time_in_seconds: int):
    with app.app_context():
        clan = Clans.query.filter_by(clan_role_id=clan_role_id).first()
        if not clan:
            await ctx.send(f"Клан с ролью ID {clan_role_id} не найден.")
            return

        quest = WeeklyClanQuest.query.filter_by(clan_id=clan.id, completed=False).first()
        if not quest:
            await ctx.send(f"У клана {clan.name} нет активного недельного задания.")
            return

        quest.voice_time = time_in_seconds
        db.session.commit()

        await ctx.send(f"Время войса для клана {clan.name} успешно обновлено: {time_in_seconds} секунд.")


@bot.command()
@white_list(white_list_role_id)
async def установить_сообщения(ctx, clan_role_id: int, message_count: int):
    with app.app_context():
        clan = Clans.query.filter_by(clan_role_id=clan_role_id).first()
        if not clan:
            await ctx.send(f"Клан с ролью ID {clan_role_id} не найден.")
            return

        quest = WeeklyClanQuest.query.filter_by(clan_id=clan.id, completed=False).first()
        if not quest:
            await ctx.send(f"У клана {clan.name} нет активного недельного задания.")
            return

        quest.messages_sent = message_count
        db.session.commit()

        await ctx.send(f"Количество сообщений для клана {clan.name} успешно обновлено: {message_count}.")

@bot.command()
@white_list(white_list_role_id)
async def недельные(ctx):
    """Создаёт недельные квесты для всех кланов."""
    with app.app_context():
        clans = Clans.query.all()
        if not clans:
            await ctx.send("Нет кланов для создания квестов.")
            return
        
        created_quests = 0
        for clan in clans:
            existing_quest = WeeklyClanQuest.query.filter_by(clan_id=clan.id, completed=False).first()
            if not existing_quest:
                new_quest = WeeklyClanQuest(
                    clan_id=clan.id,
                    messages_sent=0,
                    voice_time=0,
                    completed=False,
                    last_reset_timestamp=0
                )
                db.session.add(new_quest)
                created_quests += 1
        
        db.session.commit()
        
        if created_quests > 0:
            await ctx.send(f"Создано {created_quests} недельных квестов для всех кланов.")
        else:
            await ctx.send("Для всех кланов уже существуют недельные квесты.")

voice_start_times = defaultdict(dict)

@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel == after.channel:
        return

    with app.app_context():
        for role in member.roles:
            clan = Clans.query.filter_by(clan_role_id=role.id).first()
            if not clan:
                continue

            if after.channel is not None:
                voice_start_times[member.id] = time.time()
                print(f"{member.name} зашел в {after.channel.name}.")

            elif before.channel is not None and member.id in voice_start_times:
                start_time = voice_start_times.pop(member.id, None)
                if start_time:
                    duration = time.time() - start_time
                    duration_minutes = duration / 60

                    quest = WeeklyClanQuest.query.filter_by(clan_id=clan.id, completed=False).first()
                    if quest:
                        quest.voice_time += duration_minutes * 70
                        db.session.commit()
                        print(f"{member.name} добавил {duration_minutes * 120:.2f} минут в прогресс клана {clan.name}.")

            break

@bot.command()
@is_allowed_channel_or_user(allowed_channel_id, authorized_user)
async def задание(ctx):
    user = ctx.author

    with app.app_context():
        clan = None
        for role in user.roles:
            clan = Clans.query.filter_by(clan_role_id=role.id).first()
            if clan:
                break

        if not clan:
            await ctx.send("Вы не принадлежите ни одному клану.")
            return

        quest = WeeklyClanQuest.query.filter_by(clan_id=clan.id, completed=False).first()

        if not quest:
            await ctx.send(f"У клана {clan.name} нет активного недельного задания.")
            quest = AlwaysQuest.query.filter_by(clan_id=clan.id, user_id=user.id, completed=False).first()
            messages_progress = quest.messages_sent / 30 * 100
            voice_progress = quest.voice_time / 10 * 100

            embed = discord.Embed(
            title='Прогресс личного задания',
            description='Ваш прогресс личного задания\n——————————————————',
            color=discord.Color.orange()
            )

            if quest.task == 'text':
                embed.add_field(
                    name="Текстовое задание",
                    value=f" - {quest.messages_sent}/30 ({messages_progress:.2f}%)",
                    inline=False
                )
            elif quest.task == 'voice':
                embed.add_field(
                    name="Голосовое время",
                    value=f" - {quest.voice_time / 1:.2f}/10 минут ({voice_progress:.2f}%)",
                    inline=False
                )
            embed.set_footer(text="Продолжайте в том же духе!")

            await ctx.send(embed=embed)
            
            return

        messages_progress = quest.messages_sent / 5000 * 100
        voice_progress = quest.voice_time / (24 * 3600) * 100
        embed = discord.Embed(
            title=f"Прогресс задания клана {clan.name}",
            description='——————————————————',
            color=discord.Color.orange()
        )
        embed.add_field(
            name="Сообщения",
            value=f" - {quest.messages_sent}/5000 ({messages_progress:.2f}%)",
            inline=False
        )
        embed.add_field(
            name="Голосовое время",
            value=f"{quest.voice_time / 3600:.2f}/24 часов ({voice_progress:.2f}%)",
            inline=False
        )
        embed.set_footer(text="Продолжайте в том же духе!")

        await ctx.send(embed=embed)

        quest = AlwaysQuest.query.filter_by(clan_id=clan.id, user_id=user.id, completed=False).first()
        messages_progress = quest.messages_sent / 30 * 100
        voice_progress = quest.voice_time / 600 * 100

        embed = discord.Embed(
            title='Прогресс личного задания',
            description='Ваш прогресс личного задания\n——————————————————',
            color=discord.Color.orange()
        )

        if quest.task == 'text':
            embed.add_field(
                name="Текстовое задание",
                value=f" - {quest.messages_sent}/30 ({messages_progress:.2f}%)",
                inline=False
            )
        elif quest.task == 'voice':
            embed.add_field(
                name="Голосовое время",
                value=f" - {quest.voice_time / 600:.2f}/10 минут ({voice_progress:.2f}%)",
                inline=False
            )
        embed.set_footer(text="Продолжайте в том же духе!")

        await ctx.send(embed=embed)


#ТОПЫ КЛАНОВ
#ТОПЫ КЛАНОВ
#ТОПЫ КЛАНОВ

def get_top_clans(limit=10):
    top_clans = Clans.query.order_by(Clans.reputation.desc()).limit(limit).all()
    return top_clans

@bot.command()
@is_allowed_channel_or_user(allowed_channel_id, authorized_user)
async def топ(ctx, limit: int = 10):
    with app.app_context():
        top_clans = Clans.query.order_by(Clans.reputation.desc()).limit(limit).all()

        if not top_clans:
            await ctx.send("В базе данных нет кланов.")
            return

        embed = discord.Embed(
            title=f"Топ {limit} кланов по репутации",
            description="Список кланов с наибольшей репутацией\n——————————————————",
            color=discord.Color.gold()
        )

        for i, clan in enumerate(top_clans, 1):
            embed.add_field(
                name=f"{i}. **{clan.name}**",
                value=f" - Репутация клана: {clan.reputation}\n - Количество участников клана: {clan.clan_members}\n——————————————————",
                inline=False
            )

        await ctx.send(embed=embed)

@bot.command()
@is_allowed_channel_or_user(allowed_channel_id, authorized_user)
async def хелп(ctx):
    embed = discord.Embed(
        title='**Список доступных команд**',
        description='Вот все команды, которые доступны в боте.',
        color=discord.Color.blue()
    )

    commands_list = {
        "Основные команды": [
            "!топ - показать топ кланов по репутации",
            "!задание - показать прогресс выполнения кланового и личного задания",
            "!игра - запустить игру в крестики-нолики с ботом"
        ],
        "Административные команды": [
            "!клан - открыть меню управления кланами",
            "!обновить - обновить количество участников клана в БД",
            "!роли - показать ID всех клановых ролей",
            "!прогресс - показать прогресс выполнения всех клановых заданий",
            "!время - показать время в войсе для недельного задания",
            "!установить_войс [ID роли] [время] - установить голосовое время для клана",
            "!установить_сообщения [ID роли] [кол-во сообщений] - установить сообщения для клана",
            "!недельные - создать недельные задания для всех кланов",
            "!тег - пинг всех кланов"
        ],
        "Развлечения и мини-игры": [
            "!игра - запустить игру в крестики-нолики",
  
        ]
    }

    for category, cmds in commands_list.items():
        embed.add_field(
            name=category,
            value="\n".join(cmds),
            inline=False
        )
    
    await ctx.send(embed=embed)


@bot.command()
@white_list(white_list_role_id)
async def тег(ctx):
    with app.app_context():
        clans = Clans.query.all()

        if not clans:
            await ctx.send("В базе данных нет кланов для пинга.")
            return

        mentions = [f"<@&{clan.clan_role_id}>" for clan in clans if clan.clan_role_id]

        if not mentions:
            await ctx.send("У кланов отсутствуют role_id для пинга.")
            return

        chunk_size = 2000
        chunks = []
        current_chunk = ""

        for mention in mentions:
            if len(current_chunk) + len(mention) + 1 > chunk_size:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            current_chunk += mention + " "

        if current_chunk:
            chunks.append(current_chunk.strip())

        for chunk in chunks:
            await ctx.send(chunk)

# МИНИИГРЫ И СОБЫТИЯ
# МИНИИГРЫ И СОБЫТИЯ
# МИНИИГРЫ И СОБЫТИЯ

HISTORY_FILE = "game_history.json"
EMPTY_CELL = "⬜"

# Загружаем историю игр
def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as file:
            return json.load(file)
    return []

# Сохраняем историю игр
def save_history(history):
    with open(HISTORY_FILE, "w") as file:
        json.dump(history, file, indent=4)

# Алгоритм MinMax
def minmax(board, depth, is_maximizing):
    winner = check_winner(board)
    if winner == "O":
        return 1
    elif winner == "X":
        return -1
    elif winner == "Draw":
        return 0

    if is_maximizing:
        best_score = -float('inf')
        for i in range(9):
            if board[i] == EMPTY_CELL:
                board[i] = "O"
                score = minmax(board, depth + 1, False)
                board[i] = EMPTY_CELL
                best_score = max(score, best_score)
        return best_score
    else:
        best_score = float('inf')
        for i in range(9):
            if board[i] == EMPTY_CELL:
                board[i] = "X"
                score = minmax(board, depth + 1, True)
                board[i] = EMPTY_CELL
                best_score = min(score, best_score)
        return best_score

# Функция для ИИ (MinMax)
def get_ai_move(board):
    best_move = None
    best_score = -float('inf')
    
    for i in range(9):
        if board[i] == EMPTY_CELL:
            board[i] = "O"
            score = minmax(board, 0, False)
            board[i] = EMPTY_CELL
            if score > best_score:
                best_score = score
                best_move = i
                
    return best_move

# Проверка победителя
def check_winner(board):
    winning_combinations = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8),
        (0, 3, 6), (1, 4, 7), (2, 5, 8),
        (0, 4, 8), (2, 4, 6)
    ]
    for a, b, c in winning_combinations:
        if board[a] == board[b] == board[c] and board[a] != EMPTY_CELL:
            return board[a]
    return None if EMPTY_CELL in board else "Draw"

# Класс для игрового интерфейса
class TicTacToeView(discord.ui.View):
    def __init__(self, creator):
        super().__init__(timeout=180)
        self.board = [EMPTY_CELL] * 9
        self.current_turn = "X"
        self.creator = creator  # Создатель игры
        self.history = load_history()

        # Создание кнопок для игры
        for i in range(9):
            self.add_item(TicTacToeButton(i))

    def update_buttons(self):
        """Обновляет метки и состояние кнопок в соответствии с текущим состоянием доски."""
        for child in self.children:
            if isinstance(child, TicTacToeButton):
                child.label = self.board[child.index]
                child.disabled = self.board[child.index] != EMPTY_CELL

    async def disable_all_buttons(self, interaction):
        """Отключает все кнопки после завершения игры."""
        for child in self.children:
            if isinstance(child, TicTacToeButton):
                child.disabled = True

    async def process_turn(self, interaction, index):
        if interaction.user != self.creator:
            await interaction.response.send_message("Только создатель игры может делать ходы!", ephemeral=True)
            return

        if self.board[index] != EMPTY_CELL:
            return

        # Ход игрока
        self.board[index] = "X"
        winner = check_winner(self.board)

        # Проверка на победу
        if winner:
            await self.end_game(interaction, winner)
            return

        # Ход ИИ
        self.current_turn = "O"
        ai_move = get_ai_move(self.board)
        self.board[ai_move] = "O"

        # Проверка на победу после хода ИИ
        winner = check_winner(self.board)
        if winner:
            await self.end_game(interaction, winner)
            return

        # Смена хода на игрока
        self.current_turn = "X"
        self.update_buttons()
        await interaction.response.edit_message(content="Ваш ход!", view=self)

    async def end_game(self, interaction, winner):
        await self.disable_all_buttons(interaction)  # Отключаем кнопки
        self.update_buttons()  # Обновляем кнопки с текущими метками
        self.history.append({"board": self.board[:], "winner": winner})  # Сохраняем историю
        save_history(self.history)

        clan_message = ""

        # Проверяем, что победителем является игрок (X)
        if winner == "X":
            with app.app_context():
                for role in self.creator.roles:
                    clan = Clans.query.filter_by(clan_role_id=role.id).first()
                    if clan:
                        clan.reputation += 50  # Начисляем 50 репутации
                        db.session.commit()
                        clan_message = f"Клану {clan.name} было начислено 50 репутации!"
                        break

        # Формируем итоговое сообщение
        if winner == "Draw":
            message = "Ничья!"
        elif winner == "X":
            message = f"Игрок {winner} победил! {clan_message}"
        else:
            message = f"Игрок {winner} победил!"

        # Отправляем сообщение
        try:
            if interaction.response.is_done():
                await interaction.followup.send(content=message, view=self)
            else:
                await interaction.response.send_message(content=message, view=self)
        except discord.errors.NotFound:
            await interaction.channel.send(content=message)


class TicTacToeButton(discord.ui.Button):
    def __init__(self, index):
        super().__init__(style=discord.ButtonStyle.secondary, label=EMPTY_CELL, row=index // 3)
        self.index = index
    async def callback(self, interaction: discord.Interaction):
        view: TicTacToeView = self.view
        await view.process_turn(interaction, self.index)

# Команда для запуска игры
@bot.command()
async def игра(ctx):
    view = TicTacToeView(creator=ctx.author)  # Сохраняем создателя игры
    await ctx.send(f"Игра началась! Ваш ход, {ctx.author.mention}!", view=view)

bot.run(token)
