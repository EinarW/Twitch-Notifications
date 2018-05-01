import asyncio
import aiohttp
import discord
import json
import secret
from datetime import datetime

client = discord.Client()

# Reset all sent key values to false
with open('local.json', 'r') as fp:
    reset_values = json.load(fp)
for streams_index in reset_values['streams']:
    streams_index['sent'] = 'false'
with open('local.json', 'w') as fp:
    json.dump(reset_values, fp, indent=2)


with open('local.json', 'r') as fp:
    local = json.load(fp)


@client.event
async def on_ready():
    print('Logged in as')
    print('Name: ' + client.user.name)
    print('Client ID: ' + client.user.id)
    print('------\n')


async def dump_json():
    with open('local.json' , 'w') as fp:
        json.dump(local, fp, indent=2)


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


async def fill_ids(api):
    counter = 0

    print('\nFilling missing IDs...')
    for local_user in local['streams']:
        if local_user['id'] == "":
            for api_user in api['data']:
                if local_user['login'] == api_user['login']:
                    counter += 1
                    print('Filled missing ID for User: ' + local_user['login'] + ' : ' + api_user['id'])
                    local_user['id'] = api_user['id']

    if counter == 0:
        print('No IDs missing.')
    else:
        print('\n' + str(counter) + ' IDs filled.')

    await dump_json()


# Task runs all the time, important to keep the asyncio.sleep at the end to avoid
# Function checks response from get_streams() and sends a message to joined discord channels accordingly.
async def looped_task():
    await client.wait_until_ready()

    c_id = '9kn1me8vriegnjyxoum7yprapfi3kn'  # Client ID from Twitch Developers App
    c_secret = secret.secret  # Client Secret from Twitch Developers App

    # Loads json file containing information on channels and their subscribed streams as well as the last recorded
    # status of the streams
    counter = 0  # Counter mostly for debug
    first_startup = 1  # Prepwork

    # Check response from fecth() and messages discord channels
    while not client.is_closed:
        if first_startup:
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

            # Loop through api response and set offline stream's 'sent' key value to false
            for index in local['streams']:

                print('\nSTREAM NAME: ' + index['login'])
                print('STREAM ID: ' + index['id'])

                found_match = 0
                for api_index in api['data']:

                    # If stream is offline, set 'sent' key value to false, then save and reload the local JSON file
                    if api_index['user_id'] == index['id']:
                        print('MATCHING ID FROM API: ' + api_index['user_id'])
                        found_match = 1
                        live_counter += 1
                        live_streams.append(index['login'])

                if found_match == 0:
                    print('MATCHING ID NOT FOUND')
                    index['sent'] = 'false'
                    await dump_json()

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
                                    await client.send_message(client.get_channel(channel_id), msg)

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


@client.event
async def on_message(message):

    if message.content.startswith('!help'):
        msg = 'This bot lets you know when Lirik is live.\nHelpful, I know.'
        await client.send_message(message.channel, msg)

client.loop.create_task(looped_task())
client.run(secret.token)