import asyncio
import aiohttp
import json
import secret
import re
from discord.ext import commands
from datetime import datetime

client = commands.Bot(command_prefix='!')
client.remove_command('help')

unresolved_ids = 0

# Reset all sent key values to false
with open('local.json', 'r') as fp:
    reset_values = json.load(fp)
for streams_index in reset_values['streams']:
    streams_index['sent'] = 'false'
with open('local.json', 'w') as fp:
    json.dump(reset_values, fp, indent=2)


with open('local.json', 'r') as fp:
    local = json.load(fp)

with open('userlist.json', 'r') as fp:
    user_list = json.load(fp)

api = {}


@client.event
async def on_ready():
    print('Logged in as')
    print('Name: {}'.format(client.user.name))
    print('Client ID: {}'.format(client.user.id))
    print('------\n')


async def dump_json():
    with open('local.json' , 'w') as fp:
        json.dump(local, fp, indent=2)

    with open('userlist.json' , 'w') as fp:
        json.dump(user_list, fp, indent=2)


# Return response from twitch api
async def get_streams(c_id, session, url, response_type):

    # Param contains Client ID
    headers = {
        'Client-ID': '{}'.format(c_id)
    }

    # Gets and returns response from twitch api, using header defined above.
    async with session.get(url, headers=headers, timeout=10) as response:
        if response_type == 'text':
            return await response.text()
        elif response_type == 'json':
            return await response.json()


# Return response from twitch api
async def get_users(token, session, url, response_type):

    # Param contains Client ID
    headers = {
        'Authorization': 'Bearer {}'.format(token)
    }

    # Gets and returns response from twitch api, using header defined above.
    async with session.get(url, headers=headers, timeout=10) as response:
        if response_type == 'text':
            return await response.text()
        elif response_type == 'json':
            return await response.json()


async def make_token(client_id, client_secret):
    print('Getting token...')
    token_url = 'https://id.twitch.tv/oauth2/token?client_id={}&client_secret={}&grant_type=client_credentials'.format(
        client_id, client_secret)
    async with aiohttp.ClientSession() as session:
        async with session.post(token_url) as response:
            response = await response.json()
            token = response['access_token']
            print('Token: ' + token + '\n------')
            return token


# Make and return the Twitch streams api url with the user_logins in local.json
async def make_streams_url():
    streams = local['streams']

    url = 'https://api.twitch.tv/helix/streams?user_login='

    for index, login in enumerate(streams):
        if index == 0:
            url = url + login['login']
        else:
            url = url + '&user_login=' + login['login']

    return url


# Make and return the Twitch streams api url with the user_logins in local.json
async def make_users_url():
    stream = local['streams']

    url = 'https://api.twitch.tv/helix/users?login='

    for index, login in enumerate(stream):
        if index == 0:
            url = url + login['login']
        else:
            url = url + '&login=' + login['login']

    return url


async def fill_ids(users_response):
    global unresolved_ids
    counter = 0

    print('\nFilling missing IDs...')
    for local_user in local['streams']:
        if local_user['id'] == "":
            for user in users_response['data']:
                if local_user['login'] == user['login']:
                    counter += 1
                    print('Filled missing ID for User: ' + local_user['login'] + ' : ' + user['id'])
                    local_user['id'] = user['id']

    if counter == 0:
        print('No IDs missing.')
    else:
        print('\n' + str(counter) + ' IDs filled.')

    unresolved_ids = 0
    await dump_json()


# Task runs all the time, important to keep the asyncio.sleep at the end to avoid
# Function checks response from get_streams() and sends a message to joined discord channels accordingly.
async def looped_task():
    await client.wait_until_ready()
    global api

    c_id = '9kn1me8vriegnjyxoum7yprapfi3kn'  # Client ID from Twitch Developers App
    c_secret = secret.secret  # Client Secret from Twitch Developers App

    # Loads json file containing information on channels and their subscribed streams as well as the last recorded
    # status of the streams
    counter = 0  # Counter mostly for debug
    first_startup = 1  # Prepwork

    # Check response from fecth() and messages discord channels
    while not client.is_closed():
        if first_startup or unresolved_ids:
            users_url = await make_users_url()
            await asyncio.sleep(2)

            # Fill in missing stream IDs from api to local JSON
            token = await make_token(c_id, c_secret)  # Token to get twitch ID from all the added twitch usernames
            async with aiohttp.ClientSession() as session:
                users_response = await get_users(token, session, users_url, 'json')
            await fill_ids(users_response)

            await asyncio.sleep(2)  # Wait enough for login to print to console
            first_startup = 0

        else:
            counter += 1
            live_counter = 0
            live_streams = []
            print('\n------\nCheck #' + str(counter) + '\nTime: ' + str(datetime.now()))

            streams_url = await make_streams_url()
            async with aiohttp.ClientSession() as session:
                api = await get_streams(c_id, session, streams_url, 'json')

            # Check for streams in local['streams'] that are not in any of the channels' subscriptions and remove those
            all_subscriptions = []
            for channel_index in local['channels']:
                for subscribed in channel_index['subscribed']:
                    if subscribed not in all_subscriptions:
                        all_subscriptions.append(subscribed)

            for i, stream in enumerate(local['streams']):
                if stream['login'] not in all_subscriptions:
                    print('\nTime: ' + str(datetime.now()) + '\nNo channels subscribed to stream:\nREMOVED: ' +
                          stream['login'] + ' from local["streams"]\n')
                    stream_list = local['streams']
                    stream_list.pop(i)

                    await dump_json()

            # Check for streams in channel subscriptions that are not in the user_response
            for channel in local['channels']:
                channel_id = channel['id']
                for subscription in channel['subscribed']:
                    exists = 0
                    for user in users_response['data']:
                        if subscription == user['login']:
                            exists = 1

                    if exists == 0:
                        sub_list = channel['subscribed']
                        sub_list.remove(subscription)

                        print('\nTime: ' + str(datetime.now()))
                        print('Twitch stream does not exist: ')
                        print('REMOVED STREAM: ' + subscription + '\nCHANNEL ID: ' + str(channel_id))
                        msg = subscription + ' does not exist, removing channel from notification list.'

                        channel_to_send = client.get_channel(channel_id)
                        await channel_to_send.send(msg)

                        await dump_json()

            # Loop through api response and set offline stream's 'sent' key value to false
            # If stream is offline, set 'sent' key value to false, then save and reload the local JSON file
            for index in local['streams']:

                print('\nSTREAM NAME: ' + index['login'])
                print('STREAM ID: ' + index['id'])

                found_match = 0
                for api_index in api['data']:
                    if api_index['user_id'] == index['id']:
                        print('MATCHING ID FROM API: ' + api_index['user_id'])
                        found_match = 1
                        live_counter += 1
                        live_streams.append(index['login'])

                if found_match == 0:
                    print('MATCHING ID NOT FOUND')
                    index['sent'] = 'false'
                    index['status'] = 'offline'
                    await dump_json()

                else:
                    index['status'] = 'live'

                print('')

            streams_sent = []

            # Loop through channels and send out messages
            for channel in local['channels']:
                channel_id = channel['id']
                for subscribed_stream in channel['subscribed']:

                    # Get correct id from local JSON
                    for stream_index in local['streams']:
                        local_id = ''
                        if stream_index['login'] == subscribed_stream:
                            local_id = stream_index['id']

                        for api_index in api['data']:
                            if api_index['user_id'] == local_id:

                                status = api_index['type']

                                # If live, checks whether stream is live or vodcast, sets msg accordingly
                                # Sends message to channel, then saves sent status to json
                                if status == 'live' and stream_index['sent'] == 'false':
                                    msg = stream_index['login'] + ' is LIVE!\nhttps://www.twitch.tv/' + stream_index['login']
                                    channel_to_send = client.get_channel(channel_id)
                                    await channel_to_send.send(msg)

                                elif status == 'vodcast' and stream_index['sent'] == 'false':
                                    msg = stream_index['login'] + ' VODCAST is LIVE!\nhttps://www.twitch.tv/' + stream_index['login']
                                    await client.send_message(client.get_channel(channel_id), msg)

                                # Loop through streams_sent[], if stream is not there, then add it
                                add_sent = 1
                                for stream in streams_sent:
                                    if stream == stream_index['login']:
                                        add_sent = 0
                                if add_sent:
                                    streams_sent.append(stream_index['login'])

            for login in local['streams']:
                for stream in streams_sent:
                    if login['login'] == stream:
                        login['sent'] = 'true'

            await dump_json()

            print('Live Channels: ' + str(live_counter))
            for stream in live_streams:
                print(stream)

            await asyncio.sleep(30)  # task runs every x second(s)


@client.command()
async def help(ctx):
    u_id = ctx.message.author.id
    v_list = user_list['verified_users']

    msg = 'This bot lets you know when your favorite streamers go live.\nHelpful, I know.\n\nCommands:\n\n' \
          '!list: List your channels\n' \
          '!checklive: Check which streams are currently live\n' \
          '!add <twitch channel>: Add a twitch channel\n' \
          '!remove <twitch channel>: Remove a twitch channel\n'

    v_msg = '\n\nAs a verified user, you can verify or remove discord text channels for use with Twitch Notifications using ' \
                    'these commands:\n\n' \
                    '!addchannel: Add the text channel to the list of verified channels.\n' \
                    '!removechannel: Remove the text channel from the list of verified channels\n\n' \

    if u_id in v_list:
        msg = msg + v_msg

    await ctx.send(msg)


@client.command()
async def list(ctx):
    channel_id = ctx.message.channel.id
    channel_exists = 0
    has_subscriptions = 0

    print('\n------\n\nTime: ' + str(datetime.now()))
    print('List request from channel ' + str(channel_id))

    msg = 'You currently receive notifications for the following channels:\n'
    for channel in local['channels']:

        # Check if channel has been added to local.json
        if channel['id'] == channel_id:
            channel_exists = 1
            for stream in channel['subscribed']:
                has_subscriptions = 1
                msg = msg + '\n' + stream

    # If channel does not exist, send message to ctx and return
    if channel_exists == 0:
        msg = 'This discord channel has not been verified yet.'
        print('Could not remove stream, channel has not been added to bot.\n------\n')
        await ctx.send(msg)
        return

    elif not has_subscriptions:
        msg = 'You have not added any twitch channels.'
        print('No subscriptions added.\n------\n')
        await ctx.send(msg)
        return

    else:
        print('\n------\n')
        await ctx.send(msg)


@client.command()
async def checklive(ctx):
    c_id = ctx.message.channel.id
    streams_live = []

    for channel in local['channels']:
        if c_id == channel['id']:
            if len(channel['subscribed']) == 0:
                msg = 'You have not added any twitch channels.'
                await ctx.send(msg)
                return

    for stream in local['streams']:
        if stream['status'] == 'live':
            streams_live.append(stream['login'])

    if len(streams_live) == 1:
        msg = 'From your notifications, there is currently 1 stream live:\n\n'
        for login in streams_live:
            msg = msg + '{}\n'.format(login)

    elif len(streams_live) > 0:
        msg = 'From your notifications, there are currently {} streams live:\n\n'.format(len(streams_live))
        for login in streams_live:
            msg = msg + '{}\n'.format(login)

    else:
        msg = 'There are no streams live.'

    await ctx.send(msg)


@client.command()
async def remove(ctx, arg):
    channel_id = ctx.message.channel.id
    channel_exists = 0
    arg = str(arg.lower())

    print('\n------\n\nTime: ' + str(datetime.now()))
    print('Remove request from channel ' + str(channel_id) + ' for stream name ' + arg)

    # Check if channel has been added to local.json
    for channel in local['channels']:
        if channel['id'] == channel_id:
            channel_exists = 1

    # If channel does not exist, send message to ctx and return
    if channel_exists == 0:
        msg = 'This discord channel has not been verified yet.'
        print('Could not remove stream, channel has not been added to bot.')
        await ctx.send(msg)
        return

    if not re.match('^[a-zA-Z0-9_]+$', arg):
        msg = 'Name must not contain special characters.'
        print(msg)
        await ctx.send(msg)
        return

    # Check channel list in local.json to avoid duplicates
    for i, channel in enumerate(local['channels']):
        subscription_exists = 0

        if channel['id'] == channel_id:
            for stream in channel['subscribed']:
                if stream == arg:
                    subscription_exists = 1

            if subscription_exists:
                subscriptions = channel['subscribed']
                subscriptions.remove(arg)
                await dump_json()

                print('\nREMOVED: \nSTREAM: ' + arg + '\nCHANNEL ID: ' + str(channel_id) + '\n------\n')

                msg = 'Removed ' + arg + '.'
                await ctx.send(msg)

            else:
                print(arg + ' does not exist in channel subscribtions')

                msg = arg + ' is not currently in your notifications.'
                await ctx.send(msg)


@client.command()
async def add(ctx, arg):
    """Add a twitch stream to channel notifications"""
    global unresolved_ids
    channel_id = ctx.message.channel.id
    stream_exists = 0
    channel_exists = 0
    subscription_exists = 0
    arg = str(arg.lower())
    new_stream = {
        "login": arg,
        "sent": "false",
        "id": "",
        "status": ""
    }

    print('\n------\n\nTime: ' + str(datetime.now()))
    print('Add request from channel ' + str(channel_id) + ' for stream name ' + arg)

    if not re.match('^[a-zA-Z0-9_]+$', arg):
        msg = 'Name must not contain special characters.'
        print(msg)
        await ctx.send(msg)
        return

    # Check streams list in local.json to avoid duplicates
    for index in local['streams']:
        if index['login'] == arg:
            stream_exists = 1

    # Check channel list in local.json to avoid duplicates
    for channel in local['channels']:

        # Check if channel has been added to local.json
        if channel['id'] == channel_id:
            channel_exists = 1

            for stream in channel['subscribed']:

                # Check if stream is already in channel's subscriptions
                if stream == arg:
                    subscription_exists = 1

    # If channel does not exist, send message to ctx and return
    if channel_exists == 0:
        msg = 'This discord channel has not been verified yet.'
        print('Could not add stream, channel has not been added to bot.')
        await ctx.send(msg)
        return

    # Acts on the checks above
    if subscription_exists == 0 and stream_exists == 0:
        local.setdefault('streams', []).append(new_stream)
        unresolved_ids = 1

        for channel in local['channels']:
            if channel['id'] == channel_id:
                change = channel['subscribed']
                change.append(arg)

        await dump_json()

        print('\nADDED: \nSTREAM: ' + arg + '\nCHANNEL ID: ' + str(channel_id) + '\nADDED TO STREAMS\n------\n')

        msg = 'Adding ' + arg + ' to your notifications.'
        await ctx.send(msg)

    elif subscription_exists == 1 and stream_exists == 0:
        local.setdefault('streams', []).append(new_stream)
        unresolved_ids = 1

        await dump_json()

        print('\nADDED TO STREAMS\n------\n')

        msg = arg + ' is already in your notifications.'
        await ctx.send(msg)

    elif subscription_exists == 0 and stream_exists == 1:
        for channel in local['channels']:
            if channel['id'] == channel_id:
                change = channel['subscribed']
                change.append(arg)

        print('\nADDED: \nSTREAM: ' + arg + '\nCHANNEL ID: ' + str(channel_id) + '\n------\n')

        await dump_json()

        msg = 'Adding ' + arg + ' to your notifications.'
        await ctx.send(msg)

    elif subscription_exists == 1 and stream_exists == 1:
        print('ALREADY ADDED')
        msg = arg + ' has already been added to your notifications!'
        await ctx.send(msg)


@client.command()
async def addchannel(ctx):
    """Add channel to bot"""
    s_name = ctx.message.guild.name
    c_name = ctx.message.channel.name
    c_id = ctx.message.channel.id
    u_id = ctx.message.author.id
    u_name = ctx.message.author.name

    verified = 0
    duplicate = 0
    print('\n------\n\nTime: ' + str(datetime.now()))
    print('Add Channel request from:\nSERVER: {}\nCHANNEL: {} with ID {}'
          '\nUSER: {} with ID {}'.format(s_name, c_name, c_id, u_name, u_id))

    # Check if user is allowed to add channels
    for id in user_list['verified_users']:
        if u_id == id:
            verified = 1

    # If user can be verified, check for duplicates then add the channel
    if verified:

        # Check for duplicate channel IDs
        for channel in local['channels']:
            if channel['id'] == c_id:
                duplicate = 1

        # Act on duplicate check
        if not duplicate:
            new_channel = {
                "id": c_id,
                "guild_name": s_name,
                "channel_name": c_name,
                "added_by_name": u_name,
                "added_by_id": u_id,
                "subscribed": []
            }

            local['channels'].append(new_channel)
            await dump_json()

            msg = 'Channel added!'
            print(msg + '\n------\n')
            await ctx.send(msg)

        else:
            msg = 'Channel has already been added!'
            print(msg + '\n------\n')
            await ctx.send(msg)

    else:
        print('User is not authorized to add channels.\n------\n')
        msg = 'You are not authorized to add channels.'
        await ctx.send(msg)


@client.command()
async def removechannel(ctx):
    """Remove channel from bot"""
    s_name = ctx.message.guild.name
    c_name = ctx.message.channel.name
    c_id = ctx.message.channel.id
    u_id = ctx.message.author.id
    u_name = ctx.message.author.name

    verified = 0
    channel_exists = 0

    print('\n------\n\nTime: ' + str(datetime.now()))
    print('Remove Channel request from:\nSERVER: {}\nCHANNEL: {} with ID {}'
          '\nUSER: {} with ID {}'.format(s_name, c_name, c_id, u_name, u_id))

    # Check if user is allowed to add channels
    for id in user_list['verified_users']:
        if u_id == id:
            verified = 1

    # If user can be verified, try remove channel with correct id
    if verified:
        channel_list = local['channels']
        for channel in channel_list:
            if channel['id'] == c_id:
                channel_exists = 1
                channel_list.remove(channel)
                await dump_json()

        if channel_exists:
            msg = 'Channel removed!'
            print(msg + '\n------\n')
            await ctx.send(msg)

        else:
            msg = 'Channel has already been removed, or was never added in the first place.'
            print(msg + '\n------\n')
            await ctx.send(msg)

    else:
        print('User is not authorized to remove channels.\n------\n')
        msg = 'You are not authorized to remove channels.'
        await ctx.send(msg)


@client.command()
async def adduser(ctx, arg):
    """Add a user to verified list. This can only be done by master users."""
    s_name = ctx.message.guild.name
    c_name = ctx.message.channel.name
    c_id = ctx.message.channel.id
    u_id = ctx.message.author.id
    u_name = ctx.message.author.name

    print('\n------\n\nTime: ' + str(datetime.now()))
    print('Verify User request from:\nSERVER: {}\nCHANNEL: {} with ID {}'
          '\nUSER: {} with ID {}\nFor user ID: {}'.format(s_name, c_name, c_id, u_name, u_id, arg))


    # Check if user is master user
    if u_id not in user_list['master_users']:
        msg = 'You are not authorized to add users.'
        print('User is not a master user.')
        await ctx.send(msg)
        return

    # Make the argument into an int
    try:
        arg = int(arg)
    except ValueError:
        print('Request cancelled, invalid argument.\n------\n')
        await ctx.send("That didn't work, please try again.")
        return

    # If user is not already verified, add it
    if arg not in user_list['verified_users']:
        user_list['verified_users'].append(arg)
        await dump_json()

        msg = 'User ID {} is now verified.'.format(str(arg))
        print(msg + '\n------\n')
        await ctx.send(msg)

    else:
        msg = 'User ID {} is already verified.'.format(str(arg))
        print(msg + '\n------\n')
        await ctx.send(msg)


@client.command()
async def removeuser(ctx, arg):
    """Remove a user from verified list. This can only be done by master users."""
    s_name = ctx.message.guild.name
    c_name = ctx.message.channel.name
    c_id = ctx.message.channel.id
    u_id = ctx.message.author.id
    u_name = ctx.message.author.name

    print('\n------\n\nTime: ' + str(datetime.now()))
    print('Remove Verified User request from:\nSERVER: {}\nCHANNEL: {} with ID {}'
          '\nUSER: {} with ID {}\nFor user ID: {}'.format(s_name, c_name, c_id, u_name, u_id, arg))

    # Check if user is master user
    if u_id not in user_list['master_users']:
        msg = 'You are not authorized to remove users.'
        print('User is not a master user.')
        await ctx.send(msg)
        return

    # Make the argument into an int
    try:
        arg = int(arg)
    except ValueError:
        print('Request cancelled, invalid argument.\n------\n')
        await ctx.send("That didn't work, please try again.")
        return

    list = user_list['verified_users']
    try:
        list.remove(arg)
        await dump_json()

        msg = 'Removed user ID {} from verified users.'.format(str(arg))
        print(msg + '\n------\n')
        await ctx.send(msg)

    except ValueError:
        msg = 'User ID {} is not a verified user.'.format(str(arg))
        print(msg + '\n------\n')
        await ctx.send(msg)

@client.event
async def on_command_error(ctx, error):
    await ctx.send("That didn't work, please try again.")


client.loop.create_task(looped_task())
client.run(secret.token)
