from datetime import timedelta
from django.core.cache import cache
from django.template import RequestContext
from django.utils import timezone
from misago.models import Forum, Post, Rank, Session, Thread
from misago.readstrackers import ForumsTracker

def index(request):
    # Threads ranking
    popular_threads = []
    if request.settings['thread_ranking_size'] > 0:
        popular_threads = cache.get('thread_ranking_%s' % request.user.make_acl_key(), 'nada')
        if popular_threads == 'nada':
            popular_threads = []
            for thread in Thread.objects.filter(moderated=False).filter(deleted=False).filter(forum__in=Forum.objects.readable_forums(request.acl)).prefetch_related('forum').order_by('-score')[:request.settings['thread_ranking_size']]:
                thread.forum_name = thread.forum.name
                thread.forum_slug = thread.forum.slug
                popular_threads.append(thread)
            cache.set('thread_ranking_%s' % request.user.make_acl_key(), popular_threads, 60 * request.settings['thread_ranking_refresh'])

    # Ranks online
    ranks_list = cache.get('ranks_online', 'nada')
    if ranks_list == 'nada':
        ranks_dict = {}
        ranks_list = []
        users_list = []
        for rank in Rank.objects.filter(on_index=True).order_by('order'):
            rank_entry = {
                          'id':rank.id,
                          'name': rank.name,
                          'slug': rank.slug if rank.as_tab else '',
                          'style': rank.style,
                          'title': rank.title,
                          'online': [],
                         }
            ranks_list.append(rank_entry)
            ranks_dict[rank.pk] = rank_entry
        if ranks_dict:
            for session in Session.objects.select_related('user').filter(rank__in=ranks_dict.keys()).filter(last__gte=timezone.now() - timedelta(seconds=request.settings['sessions_tracker_sync_frequency'])).filter(user__isnull=False):
                if not session.user_id in users_list:
                    ranks_dict[session.user.rank_id]['online'].append(session.user)
                    users_list.append(session.user_id)
            # Assert we are on list
            if (request.user.is_authenticated() and request.user.rank_id in ranks_dict.keys()
                and not request.user.pk in users_list):
                    ranks_dict[request.user.rank_id]['online'].append(request.user)
                    users_list.append(request.user.pk)
            cache.set('team_users_online', users_list, request.settings['sessions_tracker_sync_frequency'])
            del ranks_dict
            del users_list
        cache.set('ranks_online', ranks_list, request.settings['sessions_tracker_sync_frequency'])

    # Users online
    users_online = {
                    'members': request.onlines.members(),
                    'all': request.onlines.all(),
                   }
    if not users_online['members'] and request.user.is_authenticated():
        users_online['members'] += 1
    if users_online['members'] > users_online['all']:
        users_online['all'] = users_online['members']
    if users_online['members'] >= users_online['all'] and request.user.is_anonymous():
        users_online['all'] += 1

    # Load reads tracker and build forums list
    reads_tracker = ForumsTracker(request.user)
    forums_list = Forum.objects.treelist(request.acl.forums, tracker=reads_tracker)
    
    # Whitelist ignored members
    Forum.objects.ignored_users(request.user, forums_list)
    
    # Render page
    return request.theme.render_to_response('index.html',
                                            {
                                             'forums_list': forums_list,
                                             'ranks_online': ranks_list,
                                             'users_online': users_online,
                                             'popular_threads': popular_threads,
                                             },
                                            context_instance=RequestContext(request));
