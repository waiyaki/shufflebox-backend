from .models import BrownBag, Hangout, SecretSanta, Profile, Group
from .serializers import (
  UserSerializer, BrownbagSerializer, HangoutSerializer, SecretSantaSerializer
)
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ParseError
from django.contrib.auth.models import User
from shufflebox import Randomizer
from dateutil.relativedelta import relativedelta, FR

from rest_framework.renderers import JSONRenderer
from django.db import IntegrityError
import datetime
import calendar
import json
import functools

HANGOUT_GROUP_LIMIT = 10


class UserView(generics.ListCreateAPIView):
    """A view for creating new users and listing them."""
    queryset = User.objects.all()
    serializer_class = UserSerializer


class ProfileView(generics.RetrieveUpdateDestroyAPIView):
    """A view for retrieving, updating and deleting a user instance."""
    queryset = User.objects.all()
    serializer_class = UserSerializer


class ShuffleView(APIView):
    """A view for handling shuffling requests from consumption clients."""

    def post(self, request):
        """
        Return a query set according to the post message status.
        """
        try:
            request_type = request.data['type']
            size = request.data['limit']

            if request_type == "brownbag":
                # Get all users IDs elligible for brownbag
                users_queryset = User.objects.filter(
                    profile__brownbag="not_done").values_list('id', flat=True)
                users = list(users_queryset)
                rand = Randomizer(users)
                next_brownbag_user = rand.get_random()
                today = datetime.date.today()
                weekday = today.weekday()
                next_friday = today + datetime.timedelta((4 - weekday) % 7)
                data = {
                    "date": str(next_friday),
                    "status": "next_in_line",
                    "user": next_brownbag_user
                }
                serializer = BrownbagSerializer(data=data)
                if serializer.is_valid():
                    serializer.save()
                    return Response(
                        serializer.data, status=status.HTTP_201_CREATED)
                return Response(
                    serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            elif request_type == "hangout":
                # Create hangout groups for the month
                size = request.data.get('limit', HANGOUT_GROUP_LIMIT)
                try:
                    data = create_hangout(group_size=size)
                except IntegrityError:
                    return Response(
                        {'message': "Hangouts for this month already exists"},
                        status=status.HTTP_400_BAD_REQUEST)
                except Exception as e:
                    return Response(
                        {'error': e}, status=status.HTTP_400_BAD_REQUEST)
                else:
                    return Response(data, status=status.HTTP_201_CREATED)

            elif request_type == "secretsanta":
                # Create all secretsanta pairs for that year
                # dummy data simulated from the core module
                users_queryset = User.objects.all().values_list(
                    'id', flat=True)
                users = list(users_queryset)
                rand = Randomizer(users)
                all_pairs = rand.create_groups(2)
                data = []
                for pair in all_pairs:
                    # write each to the secretsanta model (msg queue perhaps?)
                    if pair[1] is not None:
                        secretsanta = {
                            "date": str(datetime.datetime.now().date()),
                            "santa": pair[0],
                            "giftee": pair[1]
                        }
                    else:
                        # In the event of a pending/ unpaired user
                        # Default to admin user as the giftee
                        secretsanta = {
                            "date": str(datetime.datetime.now().date()),
                            "santa": pair[0],
                            "giftee": 1
                        }
                    data.append(secretsanta)

                serializer = SecretSantaSerializer(data=data, many=True)
                if serializer.is_valid():
                    serializer.save()
                    return Response(
                        serializer.data, status=status.HTTP_201_CREATED)
                return Response(
                    serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response(
                    "Bad Request With Wrong Unexpected Value of 'type' key",
                    status=status.HTTP_400_BAD_REQUEST)
        except KeyError:
            return Response(
                "Bad Request: Missing Either 'type' or 'limit' ",
                status=status.HTTP_400_BAD_REQUEST)


def last_friday(date):
    """Utility method to find last friday of the month using a given date."""
    year = date.year
    month = date.month
    month_start = datetime.date(year, month, 1)
    return month_start + relativedelta(
        days=calendar.monthrange(year, month)[1],
        weekday=FR(-1))


def render_json(serializer_class):
    """
    This decorator intercepts a model instance and renders it in json format.
    """
    def wrapper(func):
        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            result = func(*args, **kwargs)
            serializer = serializer_class(result)
            rendered = JSONRenderer().render(serializer.data)
            return json.loads(rendered.decode())
        return wrapped
    return wrapper


@render_json(HangoutSerializer)
def create_hangout(*, group_size=HANGOUT_GROUP_LIMIT):
    """
    Create a hangout group dated last friday of the month, given a group size.
    """
    users = User.objects.all().values_list('id', flat=True)
    rand = Randomizer(list(users))
    random_groups = rand.create_groups(group_size)
    hangout = Hangout.objects.create(date=last_friday(datetime.datetime.now()))

    for group in random_groups:
        group_object = Group.objects.create(hangout=hangout)
        for member in group:
            if member:
                group_object.members.add(member)
    return hangout


class HangoutView(generics.ListAPIView):
    """A view for creating new hangouts and listing them."""
    queryset = Hangout.objects.all()
    serializer_class = HangoutSerializer


class HangoutDetailsView(generics.RetrieveUpdateDestroyAPIView):
    """A view for retrieving, updating and deleting a hangout instance."""
    queryset = Hangout.objects.all()
    serializer_class = HangoutSerializer


class BrownbagView(generics.ListCreateAPIView):
    """A view for creating new BrownBags and listing them."""
    queryset = BrownBag.objects.all()
    serializer_class = BrownbagSerializer


class BrownbagDetailsView(generics.RetrieveUpdateDestroyAPIView):
    """A view for retrieving, updating and deleting a brownbag instance."""
    queryset = BrownBag.objects.all()
    serializer_class = BrownbagSerializer


class BrownBagUserListView(generics.ListAPIView):
    """
    A view for getting a list of users have not done brownbag
    """
    serializer_class = UserSerializer

    def get_queryset(self):
        """
        Return a list of users who haven't done brownbag yet.
        """
        return User.objects.filter(profile__brownbag="not_done")


class BrownbagNextInLineView(generics.ListAPIView):
    """This view  queries for the next in line brownbag presenter."""
    serializer_class = BrownbagSerializer

    def get(self, *args, **kwargs):
        """
        Return the brownbag entry as determined by status portion of the URL.
        """
        result = BrownBag.objects.filter(
            status="next_in_line").latest('status')
        serializer = BrownbagSerializer(result)

        return Response(serializer.data, status=status.HTTP_200_OK)


class SecretSantaView(generics.ListCreateAPIView):
    """A view for creating a new SecretSanta pair and listing all pairs."""
    queryset = SecretSanta.objects.all()
    serializer_class = SecretSantaSerializer


class SecretSantaDetailsView(generics.RetrieveUpdateDestroyAPIView):
    """A view for retrieving, updating and deleting a Secret santa instance."""
    queryset = SecretSanta.objects.all()
    serializer_class = SecretSantaSerializer
