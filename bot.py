import asyncio
import logging
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ConversationHandler, MessageHandler, filters, ContextTypes
)

from config import *
from database import *
from payments import *
from tts_handler import *
from translations import TRANSLATIONS
from call_handler import (
    make_phone_call, start_webhook_server, 
    get_call_recording, download_recording_file, get_keypress_results
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Stati conversazione
TEST_VOICE_TEXT = 1
CALL_COUNTRY, CALL_NUMBER, CALL_MESSAGE = range(10, 13)


# ============================================
# MENU PRINCIPALE
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user(user.id, user.username, user.first_name)
    
    lang = context.user_data.get('language', 'it')
    context.user_data['language'] = lang
    t = TRANSLATIONS[lang]
    
    if has_active_subscription(user.id):
        days_left = get_subscription_days_left(user.id)
        subscription_status = t["subscription_active"].format(days=days_left)
    else:
        subscription_status = t["subscription_inactive"]
    
    keyboard = [
        [InlineKeyboardButton("🎤 TEST CALL", callback_data="test_call")],
        [InlineKeyboardButton("💰 BUY PLAN", callback_data="buy_plan")],
        [InlineKeyboardButton("📞 START CALLING", callback_data="start_calling")],
        [InlineKeyboardButton("🎟️ REDEEM CODE", callback_data="redeem_menu")],
        [InlineKeyboardButton("🌐 " + t["change_language"], callback_data="change_language")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = f"{t['menu_title']}\n\n{subscription_status}\n\n{t['sections']}\n\n{t['test_call']}\n\n{t['buy_plan']}\n\n{t['start_calling']}\n\n{t['select_option']}"
    
    if update.callback_query:
        await update.callback_query.message.edit_text(message, parse_mode="Markdown", reply_markup=reply_markup)
        await update.callback_query.answer()
    else:
        await update.message.reply_text(message, parse_mode="Markdown", reply_markup=reply_markup)


async def change_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇮🇹 Italiano", callback_data="lang_it")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")],
        [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")],
        [InlineKeyboardButton("◀️ " + TRANSLATIONS[context.user_data.get('language', 'it')]["back"], callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    current_lang = context.user_data.get('language', 'it')
    t = TRANSLATIONS[current_lang]
    
    if update.callback_query:
        await update.callback_query.message.edit_text(t["language_selector"], parse_mode="Markdown", reply_markup=reply_markup)
        await update.callback_query.answer()


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.replace("lang_", "")
    context.user_data['language'] = lang
    await start(update, context)


# ============================================
# REDEEM CODE
# ============================================

async def redeem_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    lang = context.user_data.get('language', 'it')
    t = TRANSLATIONS[lang]
    
    await query.message.edit_text(
        f"🎟️ *REDEEM CODICE*\n\n"
        f"Inserisci il codice che hai ricevuto per attivare l'abbonamento LIFETIME.\n\n"
        f"Usa il comando:\n"
        f"`/redeem <CODICE>`\n\n"
        f"Esempio: `/redeem ABC123XYZ789`",
        parse_mode="Markdown"
    )


async def gen_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Solo l'admin può generare codici")
        return
    
    code = generate_redeem_code()
    await update.message.reply_text(
        f"✅ *CODICE GENERATO!*\n\n"
        f"📋 Codice: `{code}`\n\n"
        f"ℹ️ Chi lo usa otterrà abbonamento *LIFETIME* (10 anni)\n\n"
        f"Per usarlo: `/redeem {code}`",
        parse_mode="Markdown"
    )


async def redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ *USO:* `/redeem <CODICE>`\n\n"
            "Esempio: `/redeem ABC123XYZ789`",
            parse_mode="Markdown"
        )
        return
    
    code = args[0].upper()
    user_id = update.effective_user.id
    
    success = redeem_code(user_id, code)
    
    if success:
        await update.message.reply_text(
            f"🎉 *CODICE RISCATTATO CON SUCCESSO!*\n\n"
            f"✅ Abbonamento *LIFETIME* attivato!\n\n"
            f"Usa /start per iniziare.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"❌ *CODICE NON VALIDO* o già utilizzato!",
            parse_mode="Markdown"
        )


async def list_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Solo l'admin può vedere i codici")
        return
    
    codes = list_redeem_codes()
    
    if not codes:
        await update.message.reply_text("📋 Nessun codice generato.")
        return
    
    message = "📋 *LISTA CODICI REDEEM*\n\n"
    for c in codes:
        status = "✅ USATO" if c['used_by'] else "🟢 ATTIVO"
        if c['used_by']:
            message += f"• `{c['code']}` - {status} (da user {c['used_by']})\n"
        else:
            message += f"• `{c['code']}` - {status}\n"
    
    await update.message.reply_text(message, parse_mode="Markdown")


# ============================================
# TEST CALL
# ============================================

async def test_call(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get('language', 'it')
    t = TRANSLATIONS[lang]
    
    keyboard = [
        [InlineKeyboardButton("👩 " + t['female'], callback_data="test_start")],
        [InlineKeyboardButton(t['back'], callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.message.edit_text(
            f"{t['test_voice_title']}\n\n{t['test_voice_subtitle']}",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        await update.callback_query.answer()
    return TEST_VOICE_TEXT


async def test_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    lang = context.user_data.get('language', 'it')
    t = TRANSLATIONS[lang]
    
    await query.message.edit_text(t['insert_text'], parse_mode="Markdown")
    return TEST_VOICE_TEXT


async def test_generate_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    lang = context.user_data.get('language', 'it')
    t = TRANSLATIONS[lang]
    
    if len(text) < 3:
        await update.message.reply_text(t['text_too_short'])
        return TEST_VOICE_TEXT
    if len(text) > 500:
        await update.message.reply_text(t['text_too_long'])
        return TEST_VOICE_TEXT
    
    await update.message.reply_text(t['generating'].format(text=text[:100]), parse_mode="Markdown")
    
    try:
        audio_file = text_to_speech(text, "femminile", lang)
        with open(audio_file, 'rb') as audio:
            await update.message.reply_voice(audio, caption=t['test_completed'])
        
        keyboard = [[InlineKeyboardButton(t['back_to_menu'], callback_data="back_to_menu")]]
        await update.message.reply_text(t['back_to_menu'], reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await update.message.reply_text(t['error'].format(error=str(e)))
    
    return ConversationHandler.END


# ============================================
# BUY PLAN
# ============================================

async def buy_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get('language', 'it')
    t = TRANSLATIONS[lang]
    
    keyboard = []
    for plan_key, plan_data in PRICES_USD.items():
        plan_name = plan_key.replace("_", " ").title()
        keyboard.append([InlineKeyboardButton(f"💰 {plan_name} - {plan_data['usd']}$", callback_data=f"plan_{plan_key}")])
    keyboard.append([InlineKeyboardButton(t['back'], callback_data="back_to_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = f"{t['buy_plan_title']}\n\n{t['plans_list']}\n\n{t['payments_accepted']}\n\n{t['select_option']}"
    
    if update.callback_query:
        await update.callback_query.message.edit_text(message, parse_mode="Markdown", reply_markup=reply_markup)
        await update.callback_query.answer()
    else:
        await update.message.reply_text(message, parse_mode="Markdown", reply_markup=reply_markup)


async def plan_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    plan_key = query.data.replace("plan_", "")
    usd_amount = PRICES_USD[plan_key]["usd"]
    context.user_data['selected_plan'] = plan_key
    
    lang = context.user_data.get('language', 'it')
    t = TRANSLATIONS[lang]
    
    keyboard = [
        [InlineKeyboardButton("💎 SOLANA (SOL)", callback_data=f"pay_{plan_key}_SOL")],
        [InlineKeyboardButton("Ⓛ LITECOIN (LTC)", callback_data=f"pay_{plan_key}_LTC")],
        [InlineKeyboardButton(t['back'], callback_data="buy_plan")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        f"{t['plan_selected'].format(plan=plan_key.replace('_', ' ').title())}\n{t['amount'].format(amount=usd_amount)}\n\n{t['choose_crypto']}",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


async def process_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("_")
    if len(parts) == 4:
        plan_key = f"{parts[1]}_{parts[2]}"
        crypto = parts[3]
    else:
        plan_key = parts[1]
        crypto = parts[2]
    
    user_id = query.from_user.id
    usd_amount = PRICES_USD[plan_key]["usd"]
    payment_id = generate_payment_id(user_id, plan_key)
    lang = context.user_data.get('language', 'it')
    t = TRANSLATIONS[lang]
    
    if crypto == "SOL":
        amount = usd_to_sol(usd_amount)
        wallet = SOLANA_WALLET
        message = f"{t['payment_sol']}\n\n{t['amount_crypto'].format(amount=amount, crypto='SOL')}\n{t['wallet'].format(wallet=wallet)}\n{t['payment_id'].format(id=payment_id)}\n\n{t['payment_instructions'].format(amount=amount, crypto='SOL', id=payment_id)}\n\n{t['after_payment']}"
    else:
        amount = usd_to_ltc(usd_amount)
        wallet = LITECOIN_WALLET
        message = f"{t['payment_ltc']}\n\n{t['amount_crypto'].format(amount=amount, crypto='LTC')}\n{t['wallet'].format(wallet=wallet)}\n{t['payment_id'].format(id=payment_id)}\n\n{t['payment_instructions'].format(amount=amount, crypto='LTC', id=payment_id)}\n\n{t['after_payment']}"
    
    add_pending_payment(user_id, amount, plan_key, crypto, payment_id)
    context.user_data['pending_payment_id'] = payment_id
    
    keyboard = [[InlineKeyboardButton(t['back'], callback_data="buy_plan")]]
    await query.message.edit_text(message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def activate_subscription_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Comando riservato all'admin")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Uso: /activate <user_id> <days>\nEsempio: /activate 123456789 30")
        return
    
    try:
        user_id = int(args[0])
        days = int(args[1])
        
        sub_type = None
        for key, data in PRICES_USD.items():
            if data["days"] == days:
                sub_type = key
                break
        
        if not sub_type and days != 3650:
            await update.message.reply_text(f"❌ Giorni non validi. Opzioni: 3,7,30,90,180,365,3650")
            return
        
        sub_type = sub_type or "lifetime"
        activate_subscription(user_id, sub_type, days)
        await update.message.reply_text(f"✅ Abbonamento attivato per user {user_id} per {days} giorni!")
        
        try:
            await context.bot.send_message(user_id, f"🎉 Il tuo abbonamento di {days} giorni è stato attivato! Usa /start per iniziare.")
        except:
            pass
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}")


# ============================================
# START CALLING
# ============================================

async def start_calling(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = context.user_data.get('language', 'it')
    t = TRANSLATIONS[lang]
    
    if not has_active_subscription(user_id):
        keyboard = [
            [InlineKeyboardButton("💰 BUY PLAN", callback_data="buy_plan")],
            [InlineKeyboardButton(t['back'], callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.message.edit_text(
            f"{t['upgrade_required']}\n\n{t['upgrade_plans_list']}",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        await update.callback_query.answer()
        return
    
    days_left = get_subscription_days_left(user_id)
    keyboard = [
        [InlineKeyboardButton(t['italy'], callback_data="call_country_IT")],
        [InlineKeyboardButton(t['usa'], callback_data="call_country_US")],
        [InlineKeyboardButton(t['uk'], callback_data="call_country_UK")],
        [InlineKeyboardButton(t['back'], callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.message.edit_text(
        f"{t['subscription_verified'].format(days=days_left)}\n\n{t['select_country']}",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    await update.callback_query.answer()
    return CALL_COUNTRY


async def call_select_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    country = query.data.replace("call_country_", "")
    context.user_data['call_country'] = country
    lang = context.user_data.get('language', 'it')
    t = TRANSLATIONS[lang]
    prefixes = {"IT": "+39", "US": "+1", "UK": "+44"}
    prefix = prefixes.get(country, "+39")
    
    await query.message.edit_text(
        f"{t['country_selected'].format(country=country, prefix=prefix)}\n\n{t['insert_number']}",
        parse_mode="Markdown"
    )
    return CALL_NUMBER


async def call_receive_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    number = update.message.text.strip()
    lang = context.user_data.get('language', 'it')
    t = TRANSLATIONS[lang]
    
    if not number.isdigit() or len(number) < 8 or len(number) > 15:
        await update.message.reply_text(t['invalid_number'])
        return CALL_NUMBER
    
    context.user_data['call_number'] = number
    await update.message.reply_text(
        f"{t['number_saved'].format(number=number)}\n\n{t['insert_message']}",
        parse_mode="Markdown"
    )
    return CALL_MESSAGE


async def call_receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text.strip()
    lang = context.user_data.get('language', 'it')
    t = TRANSLATIONS[lang]
    
    if len(message) < 10:
        await update.message.reply_text(t['error'].format(error="Messaggio troppo corto"))
        return CALL_MESSAGE
    if len(message) > 500:
        await update.message.reply_text(t['error'].format(error="Messaggio troppo lungo"))
        return CALL_MESSAGE
    
    country = context.user_data.get('call_country', 'IT')
    number = context.user_data.get('call_number')
    prefixes = {"IT": "+39", "US": "+1", "UK": "+44"}
    prefix = prefixes.get(country, "+39")
    full_number = f"{prefix}{number}"
    
    await update.message.reply_text(
        t['calling_start'].format(country=country, number=full_number, text=message[:100]),
        parse_mode="Markdown"
    )
    
    try:
        result = make_phone_call(number, prefix, message, lang)
        
        if result['success']:
            await update.message.reply_text(
                f"✅ *CHIAMATA IN CORSO!*\n\n"
                f"📞 Numero: {full_number}\n"
                f"📱 Call SID: `{result['call_sid']}`\n\n"
                f"⏳ Attendere 30 secondi per il report...",
                parse_mode="Markdown"
            )
            
            # Aspetta 30 secondi
            await asyncio.sleep(30)
            
            # Recupera i tasti premuti
            keypresses = get_keypress_results(result['call_sid'])
            
            # Recupera la registrazione
            recording_url = get_call_recording(result['call_sid'])
            audio_file = None
            if recording_url:
                audio_file = download_recording_file(recording_url, result['call_sid'])
            
            # Costruisce report
            report = f"📊 *REPORT CHIAMATA*\n\n"
            report += f"📞 Numero: {full_number}\n"
            report += f"📱 Call SID: `{result['call_sid']}`\n\n"
            
            if keypresses:
                report += f"🔢 *TASTI PREMUTI:*\n"
                for kp in keypresses:
                    if 'digits' in kp:
                        report += f"   • Tasto `{kp['digits']}` alle {kp['timestamp'][:19]}\n"
            else:
                report += f"🔢 *TASTI PREMUTI:* Nessuno\n"
            
            await update.message.reply_text(report, parse_mode="Markdown")
            
            # Invia audio
            if audio_file and os.path.exists(audio_file):
                with open(audio_file, 'rb') as f:
                    await update.message.reply_audio(
                        f,
                        caption=f"🎙️ Registrazione chiamata\n📞 {full_number}",
                        parse_mode="Markdown"
                    )
            else:
                await update.message.reply_text("📹 *Registrazione:* Non disponibile", parse_mode="Markdown")
            
            add_call_to_history(
                user_id=update.effective_user.id,
                from_country=country,
                to_number=full_number,
                message=message,
                audio_file="",
                recording_file=result['call_sid'],
                duration=0,
                cost=0.02
            )
        else:
            await update.message.reply_text(t['error'].format(error=result.get('error', 'Errore sconosciuto')))
            
    except Exception as e:
        await update.message.reply_text(t['error'].format(error=str(e)))
    
    return ConversationHandler.END


# ============================================
# UTILITY
# ============================================

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get('language', 'it')
    t = TRANSLATIONS[lang]
    await update.message.reply_text(t['error'].format(error="Operazione annullata"))
    return ConversationHandler.END


# ============================================
# MAIN
# ============================================

async def post_init(application: Application):
    print("🤖 BOT AVVIATO ✅")
    print("=" * 50)
    print("Per generare un codice redeem: /gencode")
    print("Per riscattare un codice: /redeem CODICE")
    print("Per attivare abbonamento manuale: /activate user_id days")
    print("=" * 50)


def main():
    init_db()
    
    try:
        start_webhook_server()
    except Exception as e:
        print(f"⚠️ Webhook server non avviato: {e}")
    
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    # Conversation handler per TEST CALL
    test_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(test_call, pattern="^test_call$")],
        states={
            TEST_VOICE_TEXT: [
                CallbackQueryHandler(test_start, pattern="^test_start$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, test_generate_voice)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )
    
    # Conversation handler per CALL
    call_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_calling, pattern="^start_calling$")],
        states={
            CALL_COUNTRY: [CallbackQueryHandler(call_select_country, pattern="^call_country_")],
            CALL_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, call_receive_number)],
            CALL_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, call_receive_message)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )
    
    # Handler
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate", activate_subscription_admin))
    app.add_handler(CommandHandler("gencode", gen_code))
    app.add_handler(CommandHandler("redeem", redeem_command))
    app.add_handler(CommandHandler("listcodes", list_codes))
    
    app.add_handler(CallbackQueryHandler(buy_plan, pattern="^buy_plan$"))
    app.add_handler(CallbackQueryHandler(plan_selected, pattern="^plan_"))
    app.add_handler(CallbackQueryHandler(process_payment, pattern="^pay_"))
    app.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"))
    app.add_handler(CallbackQueryHandler(change_language, pattern="^change_language$"))
    app.add_handler(CallbackQueryHandler(set_language, pattern="^lang_"))
    app.add_handler(CallbackQueryHandler(redeem_menu, pattern="^redeem_menu$"))
    app.add_handler(test_conv)
    app.add_handler(call_conv)
    
    app.run_polling()


if __name__ == "__main__":
    main()