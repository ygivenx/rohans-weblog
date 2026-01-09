from django.db.models import Q
from .models import BlogPost, TIL, Bookmark, Tag


def _build_text_search_query(query, fields):
    """
    Build a Q object for text search across specified fields.
    
    Args:
        query: Search query string (can contain multiple words)
        fields: List of field lookups to search (e.g., ['title__icontains', 'content__icontains'])
        
    Returns:
        Q object that matches all words in the query (AND logic)
    """
    if not query:
        return Q()
    
    query_words = query.strip().split()
    if not query_words:
        return Q()
    
    text_queries = Q()
    for word in query_words:
        # Each word must appear in at least one of the specified fields
        word_query = Q()
        for field in fields:
            word_query |= Q(**{field: word})
        # All words must match (AND logic)
        text_queries &= word_query
    
    return text_queries


def _build_combined_filter(query, tag_slug, text_fields):
    """
    Build a combined filter for text search and tag filtering.
    
    Args:
        query: Search query string
        tag_slug: Optional tag slug to filter by
        text_fields: List of field lookups for text search
        
    Returns:
        Q object combining text search and tag filter
    """
    text_filter = _build_text_search_query(query, text_fields)
    
    tag_filter = Q()
    if tag_slug:
        tag_filter = Q(tags__slug=tag_slug)
    
    # Combine filters
    if query and tag_slug:
        return text_filter & tag_filter
    elif query:
        return text_filter
    elif tag_slug:
        return tag_filter
    else:
        return Q()


def search_content(query, tag_slug=None):
    """
    Perform full-text search across BlogPost, TIL, and Bookmark models.
    
    Supports searching in title and content fields, as well as filtering by tags.
    Uses case-insensitive search (icontains) which works well with SQLite for
    small to medium datasets. For larger datasets, consider implementing SQLite FTS
    or PostgreSQL full-text search.
    
    The search uses AND logic for multiple words - all words in the query must
    appear somewhere in the content (title, content, or tags).
    
    Args:
        query: Search query string (can contain multiple words)
        tag_slug: Optional tag slug to filter results by a specific tag
        
    Returns:
        Dictionary with keys 'posts', 'tils', 'bookmarks' containing querysets
        grouped by content type. Results are ordered by date (newest first).
    """
    if not query and not tag_slug:
        # Return empty querysets if no search criteria provided
        return {
            'posts': BlogPost.objects.none(),
            'tils': TIL.objects.none(),
            'bookmarks': Bookmark.objects.none(),
        }
    
    # Search in BlogPost (published only)
    # Search fields: title, content, tags
    post_filter = _build_combined_filter(
        query, tag_slug, ['title__icontains', 'content__icontains', 'tags__name__icontains']
    )
    posts = BlogPost.objects.filter(
        is_published=True
    ).filter(post_filter).distinct().order_by('-published_date', '-created_date')
    
    # Search in TIL
    # Search fields: title, content, tags
    til_filter = _build_combined_filter(
        query, tag_slug, ['title__icontains', 'content__icontains', 'tags__name__icontains']
    )
    tils = TIL.objects.filter(til_filter).distinct().order_by('-created_date')
    
    # Search in Bookmark
    # Search fields: title, description, url, tags
    bookmark_filter = _build_combined_filter(
        query, tag_slug, ['title__icontains', 'description__icontains', 'url__icontains', 'tags__name__icontains']
    )
    bookmarks = Bookmark.objects.filter(bookmark_filter).distinct().order_by('-created_date')
    
    return {
        'posts': posts,
        'tils': tils,
        'bookmarks': bookmarks,
    }
