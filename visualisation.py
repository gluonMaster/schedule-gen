import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as patches
import argparse
import os
from datetime import datetime, timedelta
import numpy as np


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Visualize the generated schedule.')
    
    parser.add_argument('schedule_file', help='Path to the Excel file with the generated schedule')
    parser.add_argument('--output_dir', default='schedule_visualizations', 
                     help='Directory to save visualizations (default: schedule_visualizations)')
    parser.add_argument('--view_type', choices=['teacher', 'group', 'room', 'day'], default='day',
                     help='Type of visualization to generate (default: day)')
    parser.add_argument('--name', 
                     help='Specific teacher, group, or room name to visualize (required for those view types)')
    
    return parser.parse_args()


def load_schedule(file_path):
    """Load schedule data from Excel file."""
    try:
        # Try to load from main Schedule sheet
        df = pd.read_excel(file_path, sheet_name='Schedule')
        return df
    except Exception as e:
        print(f"Error loading schedule: {e}")
        try:
            # Fallback to first sheet
            df = pd.read_excel(file_path)
            return df
        except Exception as e:
            print(f"Failed to load schedule: {e}")
            return None


def prepare_schedule_data(df):
    """Prepare schedule data for visualization."""
    # Convert time strings to datetime
    df['start_datetime'] = pd.to_datetime(df['start_time'], format='%H:%M')
    df['end_datetime'] = pd.to_datetime(df['end_time'], format='%H:%M')
    
    # Handle cases where end time is on the next day
    df.loc[df['end_datetime'] < df['start_datetime'], 'end_datetime'] += pd.Timedelta(days=1)
    
    # Create day index for ordering
    day_order = {'Mo': 0, 'Di': 1, 'Mi': 2, 'Do': 3, 'Fr': 4, 'Sa': 5, 'So': 6}
    df['day_idx'] = df['day'].map(day_order)
    
    return df


def create_color_mapping(categories):
    """Create a color mapping for categories."""
    import matplotlib.colors as mcolors
    
    # Use a colorful palette
    colors = plt.cm.tab20.colors + plt.cm.tab20b.colors + plt.cm.tab20c.colors
    
    # Create mapping
    mapping = {}
    for i, category in enumerate(sorted(categories)):
        mapping[category] = colors[i % len(colors)]
    
    return mapping


def visualize_day_schedule(df, output_dir):
    """
    Create a visualization of the schedule for each day.
    Each room is shown as a row, and classes are shown as colored blocks.
    """
    # Get unique days and rooms
    days = sorted(df['day'].unique(), key=lambda x: {'Mo': 0, 'Di': 1, 'Mi': 2, 'Do': 3, 'Fr': 4, 'Sa': 5, 'So': 6}.get(x, 999))
    
    # Create color mapping for subjects
    subject_colors = create_color_mapping(df['subject'].unique())
    
    for day in days:
        day_df = df[df['day'] == day].copy()
        
        if day_df.empty:
            continue
            
        rooms = sorted(day_df['room'].unique())
        
        # Create the figure
        fig, ax = plt.subplots(figsize=(15, max(10, len(rooms) * 0.5)))
        
        # Set up the y-axis for rooms
        ax.set_yticks(range(len(rooms)))
        ax.set_yticklabels(rooms)
        ax.set_ylim(-0.5, len(rooms) - 0.5)
        
        # Set up the x-axis for time
        start_time = datetime.strptime('08:00', '%H:%M')
        end_time = datetime.strptime('20:00', '%H:%M')
        ax.set_xlim(start_time, end_time)
        
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
        
        # Add grid lines
        ax.grid(True, axis='x', linestyle='--', alpha=0.7)
        
        # Plot classes
        for _, row in day_df.iterrows():
            room_idx = rooms.index(row['room'])
            
            # Create rectangle for the class
            rect = patches.Rectangle(
                (row['start_datetime'], room_idx - 0.4),
                row['end_datetime'] - row['start_datetime'],
                0.8,
                edgecolor='black',
                facecolor=subject_colors[row['subject']],
                alpha=0.9
            )
            ax.add_patch(rect)
            
            # Add text
            text_x = row['start_datetime'] + (row['end_datetime'] - row['start_datetime']) / 2
            ax.text(
                text_x, room_idx,
                f"{row['subject']}\n{row['teacher']}\n{row['group']}",
                ha='center', va='center',
                fontsize=8, fontweight='bold',
                color='black'
            )
        
        # Add title and labels
        ax.set_title(f'Schedule for {day}', fontsize=16)
        ax.set_xlabel('Time', fontsize=12)
        ax.set_ylabel('Room', fontsize=12)
        
        # Add legend for subjects
        legend_patches = [patches.Patch(color=subject_colors[subject], label=subject) 
                         for subject in sorted(subject_colors.keys())]
        ax.legend(handles=legend_patches, title='Subjects', loc='upper right', 
                 bbox_to_anchor=(1.15, 1), fontsize=8)
        
        # Adjust layout and save
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, f'schedule_{day}.png'), dpi=200, bbox_inches='tight')
        plt.close()
        
        print(f"Created visualization for {day}")


def visualize_teacher_schedule(df, teacher_name, output_dir):
    """
    Create a visualization of a teacher's schedule.
    Each day is shown as a row, and classes are shown as colored blocks.
    """
    # Filter for the specified teacher
    teacher_df = df[df['teacher'] == teacher_name].copy()
    
    if teacher_df.empty:
        print(f"No classes found for teacher: {teacher_name}")
        return
    
    # Get days with classes
    days = sorted(teacher_df['day'].unique(), key=lambda x: {'Mo': 0, 'Di': 1, 'Mi': 2, 'Do': 3, 'Fr': 4, 'Sa': 5, 'So': 6}.get(x, 999))
    
    # Create color mapping for subjects
    subject_colors = create_color_mapping(teacher_df['subject'].unique())
    
    # Create the figure
    fig, ax = plt.subplots(figsize=(15, max(8, len(days) * 1.5)))
    
    # Set up the y-axis for days
    ax.set_yticks(range(len(days)))
    ax.set_yticklabels(days)
    ax.set_ylim(-0.5, len(days) - 0.5)
    
    # Set up the x-axis for time
    start_time = datetime.strptime('08:00', '%H:%M')
    end_time = datetime.strptime('20:00', '%H:%M')
    ax.set_xlim(start_time, end_time)
    
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    
    # Add grid lines
    ax.grid(True, axis='x', linestyle='--', alpha=0.7)
    
    # Plot classes
    for _, row in teacher_df.iterrows():
        day_idx = days.index(row['day'])
        
        # Create rectangle for the class
        rect = patches.Rectangle(
            (row['start_datetime'], day_idx - 0.4),
            row['end_datetime'] - row['start_datetime'],
            0.8,
            edgecolor='black',
            facecolor=subject_colors[row['subject']],
            alpha=0.9
        )
        ax.add_patch(rect)
        
        # Add text
        text_x = row['start_datetime'] + (row['end_datetime'] - row['start_datetime']) / 2
        ax.text(
            text_x, day_idx,
            f"{row['subject']}\n{row['group']}\n{row['room']}",
            ha='center', va='center',
            fontsize=8, fontweight='bold',
            color='black'
        )
    
    # Add title and labels
    ax.set_title(f'Schedule for Teacher: {teacher_name}', fontsize=16)
    ax.set_xlabel('Time', fontsize=12)
    ax.set_ylabel('Day', fontsize=12)
    
    # Add legend for subjects
    legend_patches = [patches.Patch(color=subject_colors[subject], label=subject) 
                     for subject in sorted(subject_colors.keys())]
    ax.legend(handles=legend_patches, title='Subjects', loc='upper right', 
             bbox_to_anchor=(1.15, 1), fontsize=8)
    
    # Adjust layout and save
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f'teacher_{teacher_name.replace(" ", "_")}.png'), dpi=200, bbox_inches='tight')
    plt.close()
    
    print(f"Created visualization for teacher: {teacher_name}")


def visualize_group_schedule(df, group_name, output_dir):
    """
    Create a visualization of a group's schedule.
    Each day is shown as a row, and classes are shown as colored blocks.
    """
    # Filter for the specified group
    # Use contains instead of equality since group field might contain multiple groups
    group_df = df[df['group'].str.contains(group_name, na=False)].copy()
    
    if group_df.empty:
        print(f"No classes found for group: {group_name}")
        return
    
    # Get days with classes
    days = sorted(group_df['day'].unique(), key=lambda x: {'Mo': 0, 'Di': 1, 'Mi': 2, 'Do': 3, 'Fr': 4, 'Sa': 5, 'So': 6}.get(x, 999))
    
    # Create color mapping for subjects
    subject_colors = create_color_mapping(group_df['subject'].unique())
    
    # Create the figure
    fig, ax = plt.subplots(figsize=(15, max(8, len(days) * 1.5)))
    
    # Set up the y-axis for days
    ax.set_yticks(range(len(days)))
    ax.set_yticklabels(days)
    ax.set_ylim(-0.5, len(days) - 0.5)
    
    # Set up the x-axis for time
    start_time = datetime.strptime('08:00', '%H:%M')
    end_time = datetime.strptime('20:00', '%H:%M')
    ax.set_xlim(start_time, end_time)
    
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    
    # Add grid lines
    ax.grid(True, axis='x', linestyle='--', alpha=0.7)
    
    # Plot classes
    for _, row in group_df.iterrows():
        day_idx = days.index(row['day'])
        
        # Create rectangle for the class
        rect = patches.Rectangle(
            (row['start_datetime'], day_idx - 0.4),
            row['end_datetime'] - row['start_datetime'],
            0.8,
            edgecolor='black',
            facecolor=subject_colors[row['subject']],
            alpha=0.9
        )
        ax.add_patch(rect)
        
        # Add text
        text_x = row['start_datetime'] + (row['end_datetime'] - row['start_datetime']) / 2
        ax.text(
            text_x, day_idx,
            f"{row['subject']}\n{row['teacher']}\n{row['room']}",
            ha='center', va='center',
            fontsize=8, fontweight='bold',
            color='black'
        )
    
    # Add title and labels
    ax.set_title(f'Schedule for Group: {group_name}', fontsize=16)
    ax.set_xlabel('Time', fontsize=12)
    ax.set_ylabel('Day', fontsize=12)
    
    # Add legend for subjects
    legend_patches = [patches.Patch(color=subject_colors[subject], label=subject) 
                     for subject in sorted(subject_colors.keys())]
    ax.legend(handles=legend_patches, title='Subjects', loc='upper right', 
             bbox_to_anchor=(1.15, 1), fontsize=8)
    
    # Adjust layout and save
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f'group_{group_name.replace(" ", "_")}.png'), dpi=200, bbox_inches='tight')
    plt.close()
    
    print(f"Created visualization for group: {group_name}")


def visualize_room_schedule(df, room_name, output_dir):
    """
    Create a visualization of a room's schedule.
    Each day is shown as a row, and classes are shown as colored blocks.
    """
    # Filter for the specified room
    room_df = df[df['room'] == room_name].copy()
    
    if room_df.empty:
        print(f"No classes found for room: {room_name}")
        return
    
    # Get days with classes
    days = sorted(room_df['day'].unique(), key=lambda x: {'Mo': 0, 'Di': 1, 'Mi': 2, 'Do': 3, 'Fr': 4, 'Sa': 5, 'So': 6}.get(x, 999))
    
    # Create color mapping for subjects
    subject_colors = create_color_mapping(room_df['subject'].unique())
    
    # Create the figure
    fig, ax = plt.subplots(figsize=(15, max(8, len(days) * 1.5)))
    
    # Set up the y-axis for days
    ax.set_yticks(range(len(days)))
    ax.set_yticklabels(days)
    ax.set_ylim(-0.5, len(days) - 0.5)
    
    # Set up the x-axis for time
    start_time = datetime.strptime('08:00', '%H:%M')
    end_time = datetime.strptime('20:00', '%H:%M')
    ax.set_xlim(start_time, end_time)
    
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    
    # Add grid lines
    ax.grid(True, axis='x', linestyle='--', alpha=0.7)
    
    # Plot classes
    for _, row in room_df.iterrows():
        day_idx = days.index(row['day'])
        
        # Create rectangle for the class
        rect = patches.Rectangle(
            (row['start_datetime'], day_idx - 0.4),
            row['end_datetime'] - row['start_datetime'],
            0.8,
            edgecolor='black',
            facecolor=subject_colors[row['subject']],
            alpha=0.9
        )
        ax.add_patch(rect)
        
        # Add text
        text_x = row['start_datetime'] + (row['end_datetime'] - row['start_datetime']) / 2
        ax.text(
            text_x, day_idx,
            f"{row['subject']}\n{row['teacher']}\n{row['group']}",
            ha='center', va='center',
            fontsize=8, fontweight='bold',
            color='black'
        )
    
    # Add title and labels
    ax.set_title(f'Schedule for Room: {room_name}', fontsize=16)
    ax.set_xlabel('Time', fontsize=12)
    ax.set_ylabel('Day', fontsize=12)
    
    # Add legend for subjects
    legend_patches = [patches.Patch(color=subject_colors[subject], label=subject) 
                     for subject in sorted(subject_colors.keys())]
    ax.legend(handles=legend_patches, title='Subjects', loc='upper right', 
             bbox_to_anchor=(1.15, 1), fontsize=8)
    
    # Adjust layout and save
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f'room_{room_name.replace(".", "_")}.png'), dpi=200, bbox_inches='tight')
    plt.close()
    
    print(f"Created visualization for room: {room_name}")


def main():
    """Main function."""
    args = parse_arguments()
    
    # Check if schedule file exists
    if not os.path.exists(args.schedule_file):
        print(f"Error: Schedule file '{args.schedule_file}' does not exist.")
        return 1
    
    # Create output directory if needed
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)
    
    # Load schedule data
    print(f"Loading schedule from '{args.schedule_file}'...")
    df = load_schedule(args.schedule_file)
    
    if df is None or df.empty:
        print("Error: Failed to load schedule data.")
        return 1
    
    # Prepare data for visualization
    df = prepare_schedule_data(df)
    
    # Create visualizations based on view type
    if args.view_type == 'day':
        print("Creating day-based schedule visualizations...")
        visualize_day_schedule(df, args.output_dir)
    
    elif args.view_type == 'teacher':
        if not args.name:
            print("Error: Teacher name is required for teacher view type.")
            return 1
        
        print(f"Creating schedule visualization for teacher '{args.name}'...")
        visualize_teacher_schedule(df, args.name, args.output_dir)
    
    elif args.view_type == 'group':
        if not args.name:
            print("Error: Group name is required for group view type.")
            return 1
        
        print(f"Creating schedule visualization for group '{args.name}'...")
        visualize_group_schedule(df, args.name, args.output_dir)
    
    elif args.view_type == 'room':
        if not args.name:
            print("Error: Room name is required for room view type.")
            return 1
        
        print(f"Creating schedule visualization for room '{args.name}'...")
        visualize_room_schedule(df, args.name, args.output_dir)
    
    print(f"\nSchedule visualizations saved to: {os.path.abspath(args.output_dir)}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())